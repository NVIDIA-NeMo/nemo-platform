# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Fabric agent-spec artifact staging."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from nemo_agents_plugin.runner.fabric_artifact_staging import (
    FabricArtifactStagingError,
    stage_fabric_spec_config_files,
)
from nemo_deployments_plugin.entities import ConfigFile
from nemo_platform import NotFoundError


def _fabric_config(*, skills_paths: list[str] | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {
        "config_format": "nemo-agents-spec-v1",
        "name": "fabric-agent",
        "default_harness": "main",
        "harnesses": {
            "main": {
                "kind": "codex",
                "settings": {},
            }
        },
    }
    if skills_paths is not None:
        config["skills"] = {"paths": skills_paths}
    return config


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_without_agent_name_returns_inline_yaml() -> None:
    config = _fabric_config()
    rewritten = {**config, "gateway": "http://example"}
    result = await stage_fabric_spec_config_files(
        workspace="default",
        agent_name="",
        rewritten_agent_config=rewritten,
        agent_yaml_path="/workspace/agent.yaml",
        sdk=AsyncMock(),
    )
    assert result == [
        ConfigFile(path="/workspace/agent.yaml", content=yaml.safe_dump(rewritten, sort_keys=False)),
    ]


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_missing_fileset_falls_back() -> None:
    config = _fabric_config()
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    result = await stage_fabric_spec_config_files(
        workspace="default",
        agent_name="fabric-agent",
        rewritten_agent_config=config,
        agent_yaml_path="/workspace/agent.yaml",
        sdk=sdk,
    )

    assert len(result) == 1
    assert result[0].path == "/workspace/agent.yaml"
    sdk.download.assert_awaited_once()
    await_args = sdk.download.await_args
    assert await_args is not None
    assert await_args.kwargs["fileset"] == "fabric-agent-spec"
    assert await_args.kwargs["workspace"] == "default"


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_not_found_error_falls_back() -> None:
    config = _fabric_config()
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=NotFoundError("missing fileset", response=MagicMock(), body=None))

    result = await stage_fabric_spec_config_files(
        workspace="default",
        agent_name="fabric-agent",
        rewritten_agent_config=config,
        agent_yaml_path="/workspace/agent.yaml",
        sdk=sdk,
    )

    assert len(result) == 1
    assert result[0].path == "/workspace/agent.yaml"


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_stages_sibling_artifacts() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "agent.yaml").write_text("stale: true\n", encoding="utf-8")
        (root / "prompts").mkdir()
        (root / "prompts" / "system.md").write_text("You are helpful.\n", encoding="utf-8")
        skill_dir = root / "skills" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Review\n", encoding="utf-8")
        (root / "AGENT-SPEC.md").write_text("# Spec\n", encoding="utf-8")

    rewritten = _fabric_config(skills_paths=["skills/review"])
    rewritten["models"] = {"default": {"provider": "openai", "model": "gpt", "settings": {"base_url": "http://igw"}}}
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    result = await stage_fabric_spec_config_files(
        workspace="default",
        agent_name="fabric-agent",
        rewritten_agent_config=rewritten,
        agent_yaml_path="/workspace/agent.yaml",
        sdk=sdk,
    )

    by_path = {item.path: item.content for item in result}
    assert "/workspace/agent.yaml" in by_path
    assert "/workspace/prompts/system.md" in by_path
    assert "/workspace/skills/review/SKILL.md" in by_path
    assert "AGENT-SPEC.md" not in by_path
    loaded = yaml.safe_load(by_path["/workspace/agent.yaml"])
    assert loaded["models"]["default"]["settings"]["base_url"] == "http://igw"
    assert "stale" not in by_path["/workspace/agent.yaml"]


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_missing_fileset_rejects_configured_skills() -> None:
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=NotFoundError("missing fileset", response=MagicMock(), body=None))

    with pytest.raises(FabricArtifactStagingError, match="skills/review"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(skills_paths=["skills/review"]),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_rejects_non_utf8_artifact() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "agent.yaml").write_text("name: fabric-agent\n", encoding="utf-8")
        (root / "logo.bin").write_bytes(b"\xff\xfe\x00binary")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    with pytest.raises(FabricArtifactStagingError, match="non-UTF-8"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_rejects_oversized_fileset() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "agent.yaml").write_text("name: fabric-agent\n", encoding="utf-8")
        (root / "huge.md").write_text("x" * 1_000_000, encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    with pytest.raises(FabricArtifactStagingError, match="exceeding"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_rejects_missing_skill_path() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "agent.yaml").write_text("name: fabric-agent\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    with pytest.raises(FabricArtifactStagingError, match="skills/review"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(skills_paths=["skills/review"]),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )
