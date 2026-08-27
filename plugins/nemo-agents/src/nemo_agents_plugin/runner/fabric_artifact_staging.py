# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stage Fabric Ethos fileset artifacts for container and subprocess deployments."""

from __future__ import annotations

import asyncio
import logging
import posixpath
import shutil
import tempfile
from collections.abc import Collection
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import yaml
from nemo_agents_plugin.entities import (
    AGENT_CONFIG_FILENAME,
    AGENT_SPEC_FILENAME,
    ETHOS_FILENAME,
    MAX_ETHOS_STAGED_BYTES,
    ethos_fileset_name,
)
from nemo_deployments_plugin.entities import ConfigFile
from nemo_platform import NotFoundError as PlatformNotFoundError
from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError

logger = logging.getLogger(__name__)
_CONTRACT_FILENAMES = {ETHOS_FILENAME, AGENT_SPEC_FILENAME}


class FabricArtifactStagingError(ValueError):
    """Raised when Fabric deployment artifact staging cannot satisfy the agent config."""


class _FilesDownloader(Protocol):
    async def download(
        self,
        *,
        local_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> None: ...


async def stage_fabric_ethos_dir(
    *,
    workspace: str,
    agent_name: str,
    agent_config: dict[str, Any],
    base_dir: Path,
    sdk: _FilesDownloader | None,
) -> None:
    """Download the Ethos fileset into *base_dir* for subprocess deployments.

    Mirrors :func:`stage_fabric_ethos_config_files` for a runtime that reads the
    agent root off local disk rather than through a ConfigMap. An unavailable
    fileset is not fatal — config-only agents deploy from ``agent.yaml`` alone —
    but a config referencing skills still needs them staged.

    ``ETHOS.md`` and the legacy ``AGENT-SPEC.md`` file are dropped after
    download, matching the container path, so both runtimes see the same tree.

    The container byte cap does not apply here: it bounds ConfigMap and env
    delivery, neither of which is in this path. What lands on the platform host
    is bounded by ``_check_agent_root_bounds`` at CLI upload time only — a
    fileset written straight through the files API is unbounded here. That is
    the intended trust boundary for local subprocess mode, not an oversight.

    *base_dir* is reused when the controller restarts a subprocess deployment,
    so previously staged files are cleared first. Otherwise a file dropped from
    the fileset would survive locally, and stale skills could satisfy validation
    for a deployment that staged nothing.
    """
    preserved = _runtime_dir_names(agent_config)
    await asyncio.to_thread(_clear_staged_tree, base_dir, preserved)

    if agent_name and sdk is not None:
        fileset_name = ethos_fileset_name(agent_name)
        try:
            await sdk.download(local_path=str(base_dir), fileset=fileset_name, workspace=workspace)
        except (FileNotFoundError, PlatformNotFoundError, PluginClientNotFoundError) as exc:
            logger.info(
                "Ethos fileset %s/%s unavailable (%s); using inline agent.yaml only",
                workspace,
                fileset_name,
                exc,
            )

    staged = await asyncio.to_thread(_collect_staged_dir, base_dir, preserved)
    validate_referenced_skill_paths(agent_config, staged)


def _runtime_dir_names(agent_config: dict[str, Any]) -> set[str]:
    """Return top-level names under the agent root that the runtime owns, not staging.

    ``environment.workspace`` and ``environment.artifacts`` hold a live agent's
    output (Relay telemetry among it) and resolve relative to ``agent.yaml``, so
    restaging must not delete them.
    """
    environment = agent_config.get("environment")
    if not isinstance(environment, dict):
        return set()

    names: set[str] = set()
    for key in ("workspace", "artifacts"):
        value = environment.get(key)
        if not isinstance(value, str) or not value:
            continue
        rel = PurePosixPath(posixpath.normpath(value))
        if rel.is_absolute():
            continue
        # normpath resolves "foo/../workspace" to "workspace"; a leading ".." escapes base_dir.
        if rel.parts and rel.parts[0] != "..":
            names.add(rel.parts[0])
    return names


def _clear_staged_tree(base_dir: Path, preserved: set[str]) -> None:
    """Remove previously staged content, leaving *preserved* runtime directories.

    Deletion failures are fatal: a surviving skill tree would otherwise satisfy
    validation for a deployment that staged nothing.
    """
    if not base_dir.is_dir():
        return
    for child in base_dir.iterdir():
        if child.name in preserved:
            continue
        try:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
        except OSError as exc:
            raise FabricArtifactStagingError(
                f"Failed to remove stale Ethos artifact {child.name!r} from {base_dir}: {exc}"
            ) from exc


def _collect_staged_dir(base_dir: Path, preserved: set[str]) -> set[PurePosixPath]:
    """Return staged files relative to *base_dir*, rejecting anything that escapes it.

    ``_collect_staged_config_files`` refuses ``..`` in a staged path; this path
    writes to the platform host's filesystem rather than an inert ConfigMap, so
    it keeps the same guard. Symlinks are the reachable form here: the download
    lands real files, but a link inside the tree would resolve outside it.
    Contract Markdown files are removed for parity with the container path.

    *preserved* runtime directories are skipped: a running agent owns their
    contents, symlinks included, and staging neither writes nor validates them.
    """
    resolved_base = base_dir.resolve()
    staged: set[PurePosixPath] = set()
    for path in base_dir.rglob("*"):
        rel = path.relative_to(base_dir)
        if rel.parts[0] in preserved:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(resolved_base):
            raise FabricArtifactStagingError(
                f"Staged Ethos path {rel.as_posix()!r} escapes the agent base directory {base_dir}"
            )
        if not path.is_file():
            continue
        if path.name in _CONTRACT_FILENAMES:
            path.unlink()
            continue
        staged.add(PurePosixPath(rel.as_posix()))
    return staged


def _staged_relative_paths(base_dir: Path) -> set[PurePosixPath]:
    return {PurePosixPath(path.relative_to(base_dir).as_posix()) for path in base_dir.rglob("*") if path.is_file()}


async def stage_fabric_ethos_config_files(
    *,
    workspace: str,
    agent_name: str,
    rewritten_agent_config: dict[str, Any],
    agent_yaml_path: str,
    sdk: _FilesDownloader,
) -> list[ConfigFile]:
    """Download the Ethos fileset and return container ``config_files`` entries.

    When the fileset is unavailable, returns a single inline ``agent.yaml`` entry
    (AIRCORE-947 behavior). When available, maps every fileset file under the same
    ``base_dir`` as *agent_yaml_path*, substituting the rewritten YAML for
    ``agent.yaml``.
    """
    config_yaml = yaml.safe_dump(rewritten_agent_config, sort_keys=False)
    if not agent_name:
        return [ConfigFile(path=agent_yaml_path, content=config_yaml)]

    fileset_name = ethos_fileset_name(agent_name)
    try:
        with tempfile.TemporaryDirectory(prefix=f".fabric-ethos-{agent_name}-") as tmp:
            tmp_path = Path(tmp)
            await sdk.download(local_path=str(tmp_path), fileset=fileset_name, workspace=workspace)
            config_files = _collect_staged_config_files(
                root=tmp_path,
                agent_yaml_path=agent_yaml_path,
                rewritten_agent_yaml=config_yaml,
            )
            # Validate against what the fileset delivered, not config_files, which
            # carries the generated agent.yaml whether or not the fileset supplied one.
            delivered = {path for path in _staged_relative_paths(tmp_path) if path.name not in _CONTRACT_FILENAMES}
            validate_referenced_skill_paths(rewritten_agent_config, delivered)
            _validate_staged_size(config_files, fileset_name)
            return config_files
    except (FileNotFoundError, PlatformNotFoundError, PluginClientNotFoundError) as exc:
        logger.info(
            "Ethos fileset %s/%s unavailable (%s); using inline agent.yaml only",
            workspace,
            fileset_name,
            exc,
        )
        # A config that references skills still needs them staged, so an absent
        # fileset must fail here rather than at container start. Nothing was
        # staged from the fileset, so no skills.paths entry can resolve.
        validate_referenced_skill_paths(rewritten_agent_config, set())
        return [ConfigFile(path=agent_yaml_path, content=config_yaml)]


def _collect_staged_config_files(
    *,
    root: Path,
    agent_yaml_path: str,
    rewritten_agent_yaml: str,
) -> list[ConfigFile]:
    base_dir = PurePosixPath(agent_yaml_path).parent
    config_files: list[ConfigFile] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if ".." in rel.parts:
            raise FabricArtifactStagingError(f"Path escape in Ethos fileset: {rel.as_posix()!r}")
        if rel.name in _CONTRACT_FILENAMES:
            continue
        container_path = str(base_dir / PurePosixPath(rel.as_posix()))
        if rel.name == AGENT_CONFIG_FILENAME and container_path == agent_yaml_path:
            content = rewritten_agent_yaml
        else:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise FabricArtifactStagingError(
                    f"Ethos fileset contains non-UTF-8 file {rel.as_posix()!r}; staged artifacts must be text"
                ) from exc
        config_files.append(ConfigFile(path=container_path, content=content))

    if not any(cf.path == agent_yaml_path for cf in config_files):
        config_files.append(ConfigFile(path=agent_yaml_path, content=rewritten_agent_yaml))
    return config_files


def _validate_staged_size(config_files: list[ConfigFile], fileset_name: str) -> None:
    total = sum(len(config_file.content.encode("utf-8")) for config_file in config_files)
    if total > MAX_ETHOS_STAGED_BYTES:
        raise FabricArtifactStagingError(
            f"Ethos fileset {fileset_name!r} stages {total} bytes across {len(config_files)} files, "
            f"exceeding the {MAX_ETHOS_STAGED_BYTES} byte limit for container config delivery"
        )


def validate_referenced_skill_paths(
    agent_config: dict[str, Any],
    staged_paths: Collection[PurePosixPath],
) -> None:
    """Ensure every ``skills.paths`` entry resolves to staged content.

    *staged_paths* holds the staged files relative to the agent base directory,
    so container ``config_files`` and an on-disk base directory validate against
    one definition of "the skill is present".
    """
    skills = agent_config.get("skills")
    if not isinstance(skills, dict):
        return
    paths = skills.get("paths")
    if not isinstance(paths, list) or not paths:
        return

    for skill_path in paths:
        if not isinstance(skill_path, str) or not skill_path:
            continue
        rel = PurePosixPath(skill_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise FabricArtifactStagingError(
                f"Invalid skills.paths entry {skill_path!r}: must be a relative path under the agent base directory"
            )
        # "." normalizes to zero parts — the agent root itself, which packaging accepts.
        rel_parts = tuple(part for part in rel.parts if part != ".")
        if rel_parts:
            matched = any(staged.parts[: len(rel_parts)] == rel_parts for staged in staged_paths)
        else:
            matched = bool(staged_paths)
        if not matched:
            raise FabricArtifactStagingError(
                f"Referenced skills.paths entry {skill_path!r} was not found in staged Ethos fileset"
            )
