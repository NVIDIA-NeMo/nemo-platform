# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Fabric agent-spec artifact staging."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import yaml
from nemo_agents_plugin.runner.fabric_artifact_staging import (
    FabricArtifactStagingError,
    stage_fabric_spec_config_files,
    stage_fabric_spec_dir,
    validate_referenced_skill_paths,
)
from nemo_deployments_plugin.entities import ConfigFile
from nemo_platform_plugin.client.errors import NotFoundError
from nemo_platform_plugin.client.errors import NotFoundError as PluginClientNotFoundError


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
async def test_stage_fabric_spec_config_files_plugin_client_not_found_error_falls_back() -> None:
    config = _fabric_config()
    sdk = AsyncMock()
    response = httpx.Response(
        404,
        request=httpx.Request("GET", "http://platform/filesets/fabric-agent-spec"),
        json={"detail": "Fileset not found"},
    )
    sdk.download = AsyncMock(side_effect=PluginClientNotFoundError(response))

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


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_stages_sibling_artifacts(tmp_path: Path) -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "mcps").mkdir()
        (root / "mcps" / "calculator.py").write_text("print(1)\n", encoding="utf-8")
        skill_dir = root / "skills" / "review"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Review\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=_fabric_config(skills_paths=["skills/review"]),
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert (tmp_path / "mcps" / "calculator.py").read_text(encoding="utf-8") == "print(1)\n"
    assert (tmp_path / "skills" / "review" / "SKILL.md").exists()
    await_args = sdk.download.await_args
    assert await_args is not None
    assert await_args.kwargs["fileset"] == "fabric-agent-spec"
    assert await_args.kwargs["local_path"] == str(tmp_path)


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_missing_fileset_is_not_fatal(tmp_path: Path) -> None:
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=NotFoundError("missing fileset", response=MagicMock(), body=None))

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=_fabric_config(),
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_missing_fileset_rejects_configured_skills(tmp_path: Path) -> None:
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    with pytest.raises(FabricArtifactStagingError, match="skills/review"):
        await stage_fabric_spec_dir(
            workspace="default",
            agent_name="fabric-agent",
            agent_config=_fabric_config(skills_paths=["skills/review"]),
            base_dir=tmp_path,
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_without_downloader_skips_download(tmp_path: Path) -> None:
    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="",
        agent_config=_fabric_config(),
        base_dir=tmp_path,
        sdk=None,
    )

    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_allows_oversized_tree(tmp_path: Path) -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        (Path(local_path) / "huge.md").write_text("x" * 1_000_000, encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=_fabric_config(),
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert (tmp_path / "huge.md").exists()


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_removes_files_dropped_from_fileset(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "STALE.md").write_text("removed upstream\n", encoding="utf-8")
    (tmp_path / "agent.yaml").write_text("stale: true\n", encoding="utf-8")

    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        (Path(local_path) / "mcps").mkdir()
        (Path(local_path) / "mcps" / "calculator.py").write_text("print(1)\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=_fabric_config(),
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert not (tmp_path / "skills").exists()
    assert not (tmp_path / "agent.yaml").exists()
    assert (tmp_path / "mcps" / "calculator.py").exists()


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_missing_fileset_does_not_accept_stale_skills(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "review"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Stale\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    with pytest.raises(FabricArtifactStagingError, match="skills/review"):
        await stage_fabric_spec_dir(
            workspace="default",
            agent_name="fabric-agent",
            agent_config=_fabric_config(skills_paths=["skills/review"]),
            base_dir=tmp_path,
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_preserves_runtime_directories(tmp_path: Path) -> None:
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "events.atof.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "scratch.txt").write_text("keep\n", encoding="utf-8")
    (tmp_path / "STALE.md").write_text("drop\n", encoding="utf-8")

    config = _fabric_config()
    config["environment"] = {"workspace": "./workspace", "artifacts": "./artifacts"}

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=config,
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert (tmp_path / "artifacts" / "events.atof.jsonl").exists()
    assert (tmp_path / "workspace" / "scratch.txt").exists()
    assert not (tmp_path / "STALE.md").exists()


def test_validate_referenced_skill_paths_accepts_agent_root() -> None:
    validate_referenced_skill_paths(_fabric_config(skills_paths=["."]), {PurePosixPath("SKILL.md")})


def test_validate_referenced_skill_paths_rejects_agent_root_when_nothing_staged() -> None:
    with pytest.raises(FabricArtifactStagingError, match=r"\."):
        validate_referenced_skill_paths(_fabric_config(skills_paths=["."]), set())


def test_validate_referenced_skill_paths_does_not_match_sibling_prefix() -> None:
    with pytest.raises(FabricArtifactStagingError, match="skills/review"):
        validate_referenced_skill_paths(
            _fabric_config(skills_paths=["skills/review"]),
            {PurePosixPath("skills/review-notes/SKILL.md")},
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_preserves_runtime_dir_through_parent_traversal(tmp_path: Path) -> None:
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "scratch.txt").write_text("keep\n", encoding="utf-8")
    (tmp_path / "foo").mkdir()
    (tmp_path / "foo" / "stale.txt").write_text("drop\n", encoding="utf-8")

    config = _fabric_config()
    config["environment"] = {"workspace": "foo/../workspace", "artifacts": "../outside"}

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=config,
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert (tmp_path / "workspace" / "scratch.txt").exists()
    assert not (tmp_path / "foo").exists()


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_fails_when_stale_tree_cannot_be_removed(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    (tmp_path / "skills" / "SKILL.md").write_text("# Stale\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock()

    with patch(
        "nemo_agents_plugin.runner.fabric_artifact_staging.shutil.rmtree",
        side_effect=PermissionError("read-only"),
    ):
        with pytest.raises(FabricArtifactStagingError, match="stale agent spec artifact"):
            await stage_fabric_spec_dir(
                workspace="default",
                agent_name="fabric-agent",
                agent_config=_fabric_config(),
                base_dir=tmp_path,
                sdk=sdk,
            )

    sdk.download.assert_not_awaited()


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_missing_fileset_rejects_agent_root_skill() -> None:
    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=NotFoundError("missing fileset", response=MagicMock(), body=None))

    with pytest.raises(FabricArtifactStagingError, match=r"skills\.paths entry|was not found"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(skills_paths=["."]),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_accepts_agent_root_skill_from_fileset() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        (Path(local_path) / "SKILL.md").write_text("# Root skill\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    result = await stage_fabric_spec_config_files(
        workspace="default",
        agent_name="fabric-agent",
        rewritten_agent_config=_fabric_config(skills_paths=["."]),
        agent_yaml_path="/workspace/agent.yaml",
        sdk=sdk,
    )

    assert "/workspace/SKILL.md" in {item.path for item in result}


@pytest.mark.asyncio
async def test_stage_fabric_spec_config_files_agent_spec_md_alone_does_not_satisfy_root_skill() -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        (Path(local_path) / "AGENT-SPEC.md").write_text("# Spec\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    with pytest.raises(FabricArtifactStagingError, match="was not found"):
        await stage_fabric_spec_config_files(
            workspace="default",
            agent_name="fabric-agent",
            rewritten_agent_config=_fabric_config(skills_paths=["."]),
            agent_yaml_path="/workspace/agent.yaml",
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_drops_agent_spec_markdown(tmp_path: Path) -> None:
    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        root = Path(local_path)
        (root / "AGENT-SPEC.md").write_text("# Spec\n", encoding="utf-8")
        (root / "mcps").mkdir()
        (root / "mcps" / "calculator.py").write_text("print(1)\n", encoding="utf-8")

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=_fabric_config(),
        base_dir=tmp_path,
        sdk=sdk,
    )

    assert not (tmp_path / "AGENT-SPEC.md").exists()
    assert (tmp_path / "mcps" / "calculator.py").exists()


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_rejects_symlink_escaping_base_dir(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("nope\n", encoding="utf-8")
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    async def _fake_download(*, local_path: str, fileset: str | None, workspace: str | None) -> None:
        del fileset, workspace
        (Path(local_path) / "escape").symlink_to(outside)

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=_fake_download)

    with pytest.raises(FabricArtifactStagingError, match="escapes the agent base directory"):
        await stage_fabric_spec_dir(
            workspace="default",
            agent_name="fabric-agent",
            agent_config=_fabric_config(),
            base_dir=base_dir,
            sdk=sdk,
        )


@pytest.mark.asyncio
async def test_stage_fabric_spec_dir_allows_symlinks_inside_runtime_directories(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    base_dir = tmp_path / "base"
    (base_dir / "artifacts").mkdir(parents=True)
    (base_dir / "artifacts" / "link").symlink_to(outside)

    config = _fabric_config()
    config["environment"] = {"workspace": "./workspace", "artifacts": "./artifacts"}

    sdk = AsyncMock()
    sdk.download = AsyncMock(side_effect=FileNotFoundError("missing"))

    await stage_fabric_spec_dir(
        workspace="default",
        agent_name="fabric-agent",
        agent_config=config,
        base_dir=base_dir,
        sdk=sdk,
    )

    assert (base_dir / "artifacts" / "link").is_symlink()
