# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Stage Fabric agent-spec fileset artifacts for container and subprocess deployments."""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Collection
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

import yaml
from nemo_agents_plugin.entities import (
    AGENT_CONFIG_FILENAME,
    AGENT_SPEC_FILENAME,
    MAX_AGENT_SPEC_STAGED_BYTES,
    agent_spec_fileset_name,
)
from nemo_deployments_plugin.entities import ConfigFile
from nemo_platform import NotFoundError as PlatformNotFoundError
from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError

logger = logging.getLogger(__name__)


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


async def stage_fabric_spec_dir(
    *,
    workspace: str,
    agent_name: str,
    agent_config: dict[str, Any],
    base_dir: Path,
    sdk: _FilesDownloader | None,
) -> None:
    """Download the agent spec fileset into *base_dir* for subprocess deployments.

    Mirrors :func:`stage_fabric_spec_config_files` for a runtime that reads the
    agent root off local disk rather than through a ConfigMap. An unavailable
    fileset is not fatal — config-only agents deploy from ``agent.yaml`` alone —
    but a config referencing skills still needs them staged.

    The container byte cap does not apply here: it bounds ConfigMap and env
    delivery, neither of which is in this path.
    """
    if not agent_name or sdk is None:
        validate_referenced_skill_paths(agent_config, _staged_relative_paths(base_dir))
        return

    fileset_name = agent_spec_fileset_name(agent_name)
    try:
        await sdk.download(local_path=str(base_dir), fileset=fileset_name, workspace=workspace)
    except (FileNotFoundError, PlatformNotFoundError, PluginClientNotFoundError) as exc:
        logger.info(
            "Agent spec fileset %s/%s unavailable (%s); using inline agent.yaml only",
            workspace,
            fileset_name,
            exc,
        )
    validate_referenced_skill_paths(agent_config, _staged_relative_paths(base_dir))


def _staged_relative_paths(base_dir: Path) -> set[PurePosixPath]:
    return {PurePosixPath(path.relative_to(base_dir).as_posix()) for path in base_dir.rglob("*") if path.is_file()}


async def stage_fabric_spec_config_files(
    *,
    workspace: str,
    agent_name: str,
    rewritten_agent_config: dict[str, Any],
    agent_yaml_path: str,
    sdk: _FilesDownloader,
) -> list[ConfigFile]:
    """Download the agent spec fileset and return container ``config_files`` entries.

    When the fileset is unavailable, returns a single inline ``agent.yaml`` entry
    (AIRCORE-947 behavior). When available, maps every fileset file under the same
    ``base_dir`` as *agent_yaml_path*, substituting the rewritten YAML for
    ``agent.yaml``.
    """
    config_yaml = yaml.safe_dump(rewritten_agent_config, sort_keys=False)
    if not agent_name:
        return [ConfigFile(path=agent_yaml_path, content=config_yaml)]

    fileset_name = agent_spec_fileset_name(agent_name)
    try:
        with tempfile.TemporaryDirectory(prefix=f".fabric-spec-{agent_name}-") as tmp:
            tmp_path = Path(tmp)
            await sdk.download(local_path=str(tmp_path), fileset=fileset_name, workspace=workspace)
            config_files = _collect_staged_config_files(
                root=tmp_path,
                agent_yaml_path=agent_yaml_path,
                rewritten_agent_yaml=config_yaml,
            )
            _validate_referenced_skill_paths(rewritten_agent_config, config_files, agent_yaml_path)
            _validate_staged_size(config_files, fileset_name)
            return config_files
    except (FileNotFoundError, PlatformNotFoundError, PluginClientNotFoundError) as exc:
        logger.info(
            "Agent spec fileset %s/%s unavailable (%s); using inline agent.yaml only",
            workspace,
            fileset_name,
            exc,
        )
        inline_only = [ConfigFile(path=agent_yaml_path, content=config_yaml)]
        # A config that references skills still needs them staged, so an absent
        # fileset must fail here rather than at container start.
        _validate_referenced_skill_paths(rewritten_agent_config, inline_only, agent_yaml_path)
        return inline_only


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
            raise FabricArtifactStagingError(f"Path escape in agent spec fileset: {rel.as_posix()!r}")
        if rel.name == AGENT_SPEC_FILENAME:
            continue
        container_path = str(base_dir / PurePosixPath(rel.as_posix()))
        if rel.name == AGENT_CONFIG_FILENAME and container_path == agent_yaml_path:
            content = rewritten_agent_yaml
        else:
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise FabricArtifactStagingError(
                    f"Agent spec fileset contains non-UTF-8 file {rel.as_posix()!r}; staged artifacts must be text"
                ) from exc
        config_files.append(ConfigFile(path=container_path, content=content))

    if not any(cf.path == agent_yaml_path for cf in config_files):
        config_files.append(ConfigFile(path=agent_yaml_path, content=rewritten_agent_yaml))
    return config_files


def _validate_staged_size(config_files: list[ConfigFile], fileset_name: str) -> None:
    total = sum(len(config_file.content.encode("utf-8")) for config_file in config_files)
    if total > MAX_AGENT_SPEC_STAGED_BYTES:
        raise FabricArtifactStagingError(
            f"Agent spec fileset {fileset_name!r} stages {total} bytes across {len(config_files)} files, "
            f"exceeding the {MAX_AGENT_SPEC_STAGED_BYTES} byte limit for container config delivery"
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
        prefix = f"{rel}/"
        matched = any(str(staged) == str(rel) or str(staged).startswith(prefix) for staged in staged_paths)
        if not matched:
            raise FabricArtifactStagingError(
                f"Referenced skills.paths entry {skill_path!r} was not found in staged agent spec fileset"
            )


def _validate_referenced_skill_paths(
    agent_config: dict[str, Any],
    config_files: list[ConfigFile],
    agent_yaml_path: str,
) -> None:
    base_dir = PurePosixPath(agent_yaml_path).parent
    staged_paths = {
        PurePosixPath(config_file.path).relative_to(base_dir)
        for config_file in config_files
        if PurePosixPath(config_file.path).is_relative_to(base_dir)
    }
    validate_referenced_skill_paths(agent_config, staged_paths)
