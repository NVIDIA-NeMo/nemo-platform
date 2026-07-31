# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Deterministically resolve and copy one run before OpenShell starts."""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import local_path_from_uri
from nemo_experimentalist_plugin.experimentalist.components.repository import (
    clone_agent_repo,
    looks_like_git,
)
from nemo_experimentalist_plugin.harbor_bridge.archives import (
    create_directory_archive,
    extract_directory_archive,
)
from nemo_experimentalist_plugin.harbor_bridge.envelopes import register_dataset_envelope
from nemo_experimentalist_plugin.resolve import (
    EvolutionaryOptimizerConfig,
    ResolvedExperimentInputs,
)
from pydantic import BaseModel, ConfigDict

MANIFEST_FILENAME = "run.json"


class SandboxRunManifest(BaseModel):
    """Credential-free inputs consumed by the internal sandbox entrypoint."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    agent: str
    agent_spec: str | None = None
    insight: str | None = None
    train_dataset: str
    validation_dataset: str
    task_template: str | None = None
    workspace: str
    config: EvolutionaryOptimizerConfig
    framework_skills_dirs: list[str]


@dataclass(frozen=True, slots=True)
class PreparedOpenShellRun:
    """Host catalog plus the only directory uploaded into OpenShell."""

    root: Path
    catalog_root: Path
    sandbox_input: Path
    manifest_path: Path


def _safe_copy_directory(source: Path, destination: Path, *, scratch_root: Path) -> None:
    archive = scratch_root / f"copy-{uuid4().hex}.tar.gz"
    try:
        create_directory_archive(source, archive)
        extract_directory_archive(archive, destination)
    finally:
        archive.unlink(missing_ok=True)


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f"Prepared input file not found: {source}")
    if source.is_symlink() or source.stat().st_nlink > 1:
        raise ValueError(f"Prepared input file must not be linked: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


async def _resolved_insight(
    insight: str | None,
    *,
    destination: Path,
    client: Any,
    workspace: str,
) -> tuple[str | None, dict[str, Any] | None]:
    if insight is None:
        return None, None
    path = Path(insight).expanduser()
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Resolved insight is not valid JSON: {path}: {exc}") from exc
    else:
        if client is None:
            raise ValueError(f"Platform insight {insight!r} requires a Platform client during host preparation")
        value = await client.insights.insights.get(workspace=workspace, insight_id=insight)
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="json")
        elif isinstance(value, dict):
            payload = value
        else:
            raise ValueError(f"Platform returned an unsupported insight representation for {insight!r}")
    if not isinstance(payload, dict):
        raise ValueError("Resolved insight must be a JSON object")
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination.name, payload


async def _materialize_agent(
    source: str,
    *,
    destination: Path,
    host_work: Path,
    scratch_root: Path,
    clone_depth: int | None,
) -> None:
    if looks_like_git(source):
        checkout = host_work / "agent-checkout"
        provenance = await asyncio.to_thread(clone_agent_repo, source, checkout, clone_depth=clone_depth)
        resolved = checkout if provenance.agent_path == "." else checkout / provenance.agent_path
    else:
        resolved = Path(source).expanduser().resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Resolved agent directory not found: {resolved}")
    _safe_copy_directory(resolved, destination, scratch_root=scratch_root)


async def prepare_openshell_run(
    inputs: ResolvedExperimentInputs,
    *,
    experiment_dir: Path,
    client: Any,
) -> PreparedOpenShellRun:
    """Create a host-only catalog and credential-free sandbox input snapshot."""
    if inputs.config.storage.archive_candidates or inputs.config.storage.publish_winner:
        raise ValueError(
            "OpenShell execution does not support source-control archival or winner publishing; "
            "disable storage.archive_candidates and storage.publish_winner"
        )

    root = experiment_dir.expanduser().resolve() / "openshell-runtime"
    if root.exists():
        raise FileExistsError(f"OpenShell runtime directory already exists: {root}")
    catalog_root = root / "host" / "catalog"
    host_work = root / "host" / "work"
    scratch_root = root / "host" / "scratch"
    sandbox_input = root / "input"
    scratch_root.mkdir(parents=True)
    sandbox_input.mkdir(parents=True)

    try:
        dataset_paths: dict[str, str] = {}
        for name, reference in (
            ("train", inputs.train_dataset),
            ("validation", inputs.validation_dataset),
        ):
            source = local_path_from_uri(reference.uri, context=f"{name} dataset").resolve()
            registered = register_dataset_envelope(
                source,
                catalog_root=catalog_root,
                name=name,
                provenance=reference.uri,
            )
            target = sandbox_input / "datasets" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            _safe_copy_directory(registered.dataset_path, target, scratch_root=scratch_root)
            dataset_paths[name] = target.relative_to(sandbox_input).as_posix()

        template_relative = None
        if inputs.task_template is not None:
            template_source = local_path_from_uri(
                inputs.task_template.uri,
                context="task template",
            ).resolve()
            template = register_dataset_envelope(
                template_source,
                catalog_root=catalog_root,
                name="task-template",
                provenance=inputs.task_template.uri,
            )
            target = sandbox_input / "task-template"
            _safe_copy_directory(template.dataset_path, target, scratch_root=scratch_root)
            template_relative = target.relative_to(sandbox_input).as_posix()

        insight_relative, insight_payload = await _resolved_insight(
            inputs.insight,
            destination=sandbox_input / "insight.json",
            client=client,
            workspace=inputs.workspace,
        )
        agent_source = inputs.agent
        if agent_source is None and insight_payload is not None:
            raw_agent = insight_payload.get("agent")
            agent_source = raw_agent if isinstance(raw_agent, str) and raw_agent else None
        if agent_source is None:
            raise ValueError("Host preparation could not resolve an agent from flags, profile, or insight")
        agent_target = sandbox_input / "agent"
        await _materialize_agent(
            agent_source,
            destination=agent_target,
            host_work=host_work,
            scratch_root=scratch_root,
            clone_depth=inputs.config.source.clone_depth,
        )

        agent_spec_relative = None
        if inputs.agent_spec is not None:
            target = sandbox_input / "AGENT-SPEC.md"
            _copy_file(Path(inputs.agent_spec).expanduser(), target)
            agent_spec_relative = target.relative_to(sandbox_input).as_posix()

        skills_relatives: list[str] = []
        for index, source in enumerate(inputs.framework_skills_dirs, start=1):
            target = sandbox_input / "framework-skills" / f"{index:03d}-{source.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            _safe_copy_directory(source.expanduser().resolve(), target, scratch_root=scratch_root)
            skills_relatives.append(target.relative_to(sandbox_input).as_posix())

        manifest = SandboxRunManifest(
            agent=agent_target.relative_to(sandbox_input).as_posix(),
            agent_spec=agent_spec_relative,
            insight=insight_relative,
            train_dataset=dataset_paths["train"],
            validation_dataset=dataset_paths["validation"],
            task_template=template_relative,
            workspace=inputs.workspace,
            config=inputs.config,
            framework_skills_dirs=skills_relatives,
        )
        manifest_path = sandbox_input / MANIFEST_FILENAME
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    except BaseException:
        shutil.rmtree(root, ignore_errors=True)
        raise

    return PreparedOpenShellRun(
        root=root,
        catalog_root=catalog_root,
        sandbox_input=sandbox_input,
        manifest_path=manifest_path,
    )
