# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Fabric package artifact validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nemo_agents_plugin.container.fabric_validator as fabric_validator
import pytest
from nemo_agents_plugin.agent_config import AgentConfig
from nemo_agents_plugin.container.fabric_validator import (
    FabricPackageArtifactError,
    FabricPackageValidationError,
    validate_fabric_agent_package,
    validate_fabric_package_artifacts,
)


def _agent_config(*skill_paths: str) -> AgentConfig:
    return AgentConfig.model_validate(
        {
            "config_format": "nemo-agents-spec-v1",
            "name": "packaged-agent",
            "default_harness": "codex",
            "harnesses": {"codex": {"kind": "codex"}},
            "skills": {"paths": list(skill_paths)},
        }
    )


def _agent_config_path(context_dir: Path, relative_path: str = "agent.yaml") -> Path:
    path = context_dir / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("config_format: nemo-agents-spec-v1\n")
    return path


def _skill(directory: Path) -> Path:
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text("# Packaged skill\n")
    return directory


def _write_package_config(path: Path, *skill_paths: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_agent_config(*skill_paths).model_dump_json())
    return path


@pytest.mark.asyncio
class TestValidateFabricAgentPackage:
    async def test_loads_translates_plans_and_validates_artifacts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml", "../skills/review")
        _skill(tmp_path / "skills" / "review")
        translated_config = object()
        calls: dict[str, Any] = {}

        def _translate(config: AgentConfig) -> object:
            calls["translated_agent_config"] = config
            return translated_config

        async def _plan(config: object, *, base_dir: Path, fabric: Any | None = None) -> object:
            calls["planned_config"] = config
            calls["base_dir"] = base_dir
            calls["fabric"] = fabric
            return {"plan": "ok"}

        monkeypatch.setattr(fabric_validator, "translate_agent_config", _translate)
        monkeypatch.setattr(fabric_validator, "plan_fabric_config", _plan)

        result = await validate_fabric_agent_package(
            agent_config_path,
            context_dir=tmp_path,
            fabric="fabric-client",
        )

        assert result.agent_config is calls["translated_agent_config"]
        assert result.fabric_config is translated_config
        assert result.plan == {"plan": "ok"}
        assert calls["planned_config"] is translated_config
        assert calls["base_dir"] == agent_config_path.parent.resolve()
        assert calls["fabric"] == "fabric-client"

    async def test_runs_plan_without_doctor(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        translated_config = object()

        class _PlanOnlyFabric:
            def __init__(self) -> None:
                self.plan_calls: list[tuple[object, Path]] = []

            def plan(self, config: object, *, base_dir: Path) -> object:
                self.plan_calls.append((config, base_dir))
                return {"plan": "ok"}

            async def doctor(self, config: object, *, base_dir: Path) -> object:
                raise AssertionError(f"doctor must not run for package validation: {config}, {base_dir}")

        fabric = _PlanOnlyFabric()
        monkeypatch.setattr(fabric_validator, "translate_agent_config", lambda config: translated_config)

        result = await validate_fabric_agent_package(
            agent_config_path,
            context_dir=tmp_path,
            fabric=fabric,
        )

        assert result.plan == {"plan": "ok"}
        assert fabric.plan_calls == [(translated_config, agent_config_path.parent.resolve())]

    async def test_wraps_schema_error(self, tmp_path: Path) -> None:
        invalid_config = tmp_path / "invalid.yaml"
        invalid_config.write_text("name: missing-required-fields\n")

        with pytest.raises(FabricPackageValidationError, match="Invalid agent config"):
            await validate_fabric_agent_package(invalid_config, context_dir=tmp_path)

    async def test_wraps_translation_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        valid_config = _write_package_config(tmp_path / "agent.yaml")

        def _translation_failure(config: AgentConfig) -> object:
            del config
            raise fabric_validator.FabricTranslationError("unsupported harness")

        monkeypatch.setattr(fabric_validator, "translate_agent_config", _translation_failure)
        with pytest.raises(FabricPackageValidationError, match="unsupported harness"):
            await validate_fabric_agent_package(valid_config, context_dir=tmp_path)

    async def test_wraps_plan_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        valid_config = _write_package_config(tmp_path / "agent.yaml")
        monkeypatch.setattr(fabric_validator, "translate_agent_config", lambda config: object())

        async def _plan_failure(config: object, *, base_dir: Path, fabric: Any | None = None) -> object:
            del config, base_dir, fabric
            raise fabric_validator.FabricValidationError("Fabric plan failed: invalid config")

        monkeypatch.setattr(fabric_validator, "plan_fabric_config", _plan_failure)
        with pytest.raises(FabricPackageValidationError, match="Fabric plan failed: invalid config"):
            await validate_fabric_agent_package(valid_config, context_dir=tmp_path)

    async def test_surfaces_artifact_validation_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        agent_config_path = _write_package_config(tmp_path / "agent.yaml", "skills/missing")
        monkeypatch.setattr(fabric_validator, "translate_agent_config", lambda config: object())

        async def _plan(config: object, *, base_dir: Path, fabric: Any | None = None) -> object:
            del config, base_dir, fabric
            return {"plan": "ok"}

        monkeypatch.setattr(fabric_validator, "plan_fabric_config", _plan)

        with pytest.raises(FabricPackageArtifactError, match="skills/missing"):
            await validate_fabric_agent_package(agent_config_path, context_dir=tmp_path)


class TestFabricBuilderValidationHook:
    def test_validates_with_selected_build_context(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "fabric-agent"\nversion = "1.0.0"\n')
        calls: list[tuple[Path, Path]] = []

        async def _validate(agent_config: Path, *, context_dir: Path) -> object:
            calls.append((agent_config, context_dir))
            return object()

        monkeypatch.setattr(fabric_validator, "validate_fabric_agent_package", _validate)

        with pytest.raises(ValueError, match="not implemented yet"):
            build_fabric_agent_image(agent_config_path, pyproject=pyproject)

        assert calls == [(agent_config_path, tmp_path.resolve())]

    def test_skip_validation_bypasses_hook(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")

        async def _unexpected_validation(agent_config: Path, *, context_dir: Path) -> object:
            raise AssertionError(f"unexpected validation for {agent_config} in {context_dir}")

        monkeypatch.setattr(fabric_validator, "validate_fabric_agent_package", _unexpected_validation)

        with pytest.raises(ValueError, match="not implemented yet"):
            build_fabric_agent_image(agent_config_path, skip_validation=True)


class TestValidateFabricPackageArtifacts:
    def test_accepts_no_skills(self, tmp_path: Path) -> None:
        agent_config_path = _agent_config_path(tmp_path)

        validate_fabric_package_artifacts(
            _agent_config(),
            agent_config_path=agent_config_path,
            context_dir=tmp_path,
        )

    def test_accepts_skill_relative_to_nested_agent_config(self, tmp_path: Path) -> None:
        agent_config_path = _agent_config_path(tmp_path, "configs/agent.yaml")
        _skill(tmp_path / "skills" / "review")

        validate_fabric_package_artifacts(
            _agent_config("../skills/review"),
            agent_config_path=agent_config_path,
            context_dir=tmp_path,
        )

    def test_rejects_absolute_skill_path(self, tmp_path: Path) -> None:
        agent_config_path = _agent_config_path(tmp_path)
        absolute_skill = _skill(tmp_path / "skills" / "review")

        with pytest.raises(FabricPackageArtifactError, match="must be relative to agent.yaml"):
            validate_fabric_package_artifacts(
                _agent_config(str(absolute_skill)),
                agent_config_path=agent_config_path,
                context_dir=tmp_path,
            )

    def test_rejects_missing_skill_and_manifest(self, tmp_path: Path) -> None:
        agent_config_path = _agent_config_path(tmp_path)
        (tmp_path / "skills" / "empty").mkdir(parents=True)

        with pytest.raises(FabricPackageArtifactError) as error_info:
            validate_fabric_package_artifacts(
                _agent_config("skills/missing", "skills/empty"),
                agent_config_path=agent_config_path,
                context_dir=tmp_path,
            )

        message = str(error_info.value)
        assert "skills/missing" in message
        assert "does not exist" in message
        assert "skills/empty" in message
        assert "does not contain SKILL.md" in message

    def test_rejects_skill_outside_context(self, tmp_path: Path) -> None:
        context_dir = tmp_path / "project"
        context_dir.mkdir()
        agent_config_path = _agent_config_path(context_dir)
        _skill(tmp_path / "shared-skill")

        with pytest.raises(FabricPackageArtifactError, match="resolves outside Docker build context"):
            validate_fabric_package_artifacts(
                _agent_config("../shared-skill"),
                agent_config_path=agent_config_path,
                context_dir=context_dir,
            )

    def test_rejects_symlink_that_escapes_context(self, tmp_path: Path) -> None:
        context_dir = tmp_path / "project"
        context_dir.mkdir()
        agent_config_path = _agent_config_path(context_dir)
        external_skill = _skill(tmp_path / "external-skill")
        skills_dir = context_dir / "skills"
        skills_dir.mkdir()
        (skills_dir / "external").symlink_to(external_skill, target_is_directory=True)

        with pytest.raises(FabricPackageArtifactError, match="resolves outside Docker build context"):
            validate_fabric_package_artifacts(
                _agent_config("skills/external"),
                agent_config_path=agent_config_path,
                context_dir=context_dir,
            )

    def test_rejects_agent_config_outside_context(self, tmp_path: Path) -> None:
        context_dir = tmp_path / "project"
        context_dir.mkdir()
        agent_config_path = _agent_config_path(tmp_path, "agent.yaml")

        with pytest.raises(FabricPackageArtifactError, match="agent config .* is outside Docker build context"):
            validate_fabric_package_artifacts(
                _agent_config(),
                agent_config_path=agent_config_path,
                context_dir=context_dir,
            )
