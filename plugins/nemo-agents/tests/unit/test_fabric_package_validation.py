# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for Fabric package artifact validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import nemo_agents_plugin.container.fabric_validator as fabric_validator
import pytest
import typer
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


def _image_metadata() -> dict[str, str]:
    return {
        "agent_name": "fabric-agent",
        "agent_id": "abc123",
        "agent_version": "1.0.0",
        "agent_author": "Agent Author",
        "agent_framework": "nemo_platform_agent",
        "build_timestamp": "2026-08-01T00:00:00+00:00",
        "description": "Fabric agent",
        "licenses": "Apache-2.0",
        "revision": "revision",
        "source": "https://example.com/fabric-agent.git",
    }


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
    @pytest.fixture(autouse=True)
    def _stub_docker_build(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder

        monkeypatch.setattr(builder, "docker_build", lambda **kwargs: str(kwargs["tag"]))

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

        build_fabric_agent_image(agent_config_path, pyproject=pyproject)

        assert calls == [(agent_config_path, tmp_path.resolve())]

    def test_uses_agent_config_directory_without_pyproject(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml")
        calls: list[tuple[Path, Path]] = []

        async def _validate(agent_config: Path, *, context_dir: Path) -> object:
            calls.append((agent_config, context_dir))
            return object()

        monkeypatch.setattr(fabric_validator, "validate_fabric_agent_package", _validate)

        build_fabric_agent_image(agent_config_path)

        assert calls == [(agent_config_path, agent_config_path.parent.resolve())]

    def test_skip_validation_bypasses_hook(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")

        async def _unexpected_validation(agent_config: Path, *, context_dir: Path) -> object:
            raise AssertionError(f"unexpected validation for {agent_config} in {context_dir}")

        monkeypatch.setattr(fabric_validator, "validate_fabric_agent_package", _unexpected_validation)

        build_fabric_agent_image(agent_config_path, skip_validation=True)

    def test_resolves_shared_build_settings(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        calls: list[tuple[str, str | None]] = []

        def _resolve(name: str, explicit: str | None = None) -> str:
            calls.append((name, explicit))
            return f"resolved-{name}"

        monkeypatch.setattr(template, "resolve_value", _resolve)
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        build_fabric_agent_image(
            agent_config_path,
            tag="fabric-agent:test",
            base_image_url="registry.example/base",
            base_image_tag="release",
            python_version="3.13",
            uv_version="0.8.15",
            skip_validation=True,
        )

        assert calls == [
            ("base_image_url", "registry.example/base"),
            ("base_image_tag", "release"),
            ("python_version", "3.13"),
            ("uv_version", "0.8.15"),
        ]

    def test_extracts_metadata_and_derives_default_tag(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder
        import nemo_agents_plugin.container.metadata as metadata
        import nemo_agents_plugin.container.template as template

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "fabric-agent"\nversion = "1.0.0"\n')
        extracted_meta = _image_metadata()
        metadata_calls: list[dict[str, object]] = []
        tag_calls: list[dict[str, str]] = []

        def _extract(
            agent_config: Path,
            project: Path | None,
            **kwargs: object,
        ) -> dict[str, str]:
            metadata_calls.append({"agent_config": agent_config, "pyproject": project, **kwargs})
            return extracted_meta

        def _default_tag(meta: dict[str, str]) -> str:
            tag_calls.append(meta)
            return "fabric-agent-abc123:1.0.0"

        monkeypatch.setattr(metadata, "extract_agent_metadata", _extract)
        monkeypatch.setattr(builder, "_default_tag_from_meta", _default_tag)
        monkeypatch.setattr(template, "get_contract_version", lambda: "1.0.0")

        result = builder.build_fabric_agent_image(
            agent_config_path,
            pyproject=pyproject,
            base_image_url="registry.example/base",
            base_image_tag="release",
            python_version="3.13",
            uv_version="0.8.15",
            agent_version="2.0.0",
            agent_author="Agent Author",
            skip_validation=True,
        )

        assert metadata_calls == [
            {
                "agent_config": agent_config_path,
                "pyproject": pyproject,
                "agent_version": "2.0.0",
                "agent_author": "Agent Author",
                "build_env": {
                    "agent_framework": "nemo_platform_agent",
                    "contract_version": "1.0.0",
                    "nemo_relay_cli_version": "0.6.0",
                    "base_image_url": "registry.example/base",
                    "base_image_tag": "release",
                    "python_version": "3.13",
                    "uv_version": "0.8.15",
                },
            }
        ]
        assert tag_calls == [extracted_meta]
        assert result == "fabric-agent-abc123:1.0.0"

    def test_default_tag_uses_fabric_name_and_runtime_identity(self, tmp_path: Path) -> None:
        from nemo_agents_plugin.container.builder import build_fabric_agent_image
        from nemo_agents_plugin.container.metadata import (
            NEMO_PLATFORM_AGENT_FRAMEWORK,
            extract_agent_metadata,
        )
        from nemo_agents_plugin.container.template import (
            PINNED_NEMO_RELAY_CLI_VERSION,
            get_contract_version,
        )

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        build_env = {
            "agent_framework": NEMO_PLATFORM_AGENT_FRAMEWORK,
            "contract_version": get_contract_version(),
            "nemo_relay_cli_version": PINNED_NEMO_RELAY_CLI_VERSION,
            "base_image_url": "registry.example/base",
            "base_image_tag": "release",
            "python_version": "3.13",
            "uv_version": "0.8.15",
        }
        expected_metadata = extract_agent_metadata(
            agent_config_path,
            agent_version="2.0.0",
            agent_author="Agent Author",
            build_env=build_env,
        )

        result = build_fabric_agent_image(
            agent_config_path,
            base_image_url="registry.example/base",
            base_image_tag="release",
            python_version="3.13",
            uv_version="0.8.15",
            agent_version="2.0.0",
            agent_author="Agent Author",
            skip_validation=True,
        )

        assert result == f"packaged-agent-{expected_metadata['agent_id']}:2.0.0"

    def test_renders_generated_dockerfile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "fabric-agent"\nversion = "1.0.0"\n')
        image_metadata = _image_metadata()
        render_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
        build_calls: list[dict[str, object]] = []

        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: image_metadata)

        def _render(*args: object, **kwargs: object) -> str:
            render_calls.append((args, kwargs))
            return "FROM scratch\n"

        def _build(**kwargs: object) -> str:
            dockerfile = kwargs["dockerfile"]
            assert isinstance(dockerfile, Path)
            assert dockerfile.read_text() == "FROM scratch\n"
            build_calls.append(kwargs)
            return "fabric-agent:test"

        monkeypatch.setattr(template, "render_fabric_dockerfile", _render)
        monkeypatch.setattr(builder, "docker_build", _build)

        result = build_fabric_agent_image(
            agent_config_path,
            pyproject=pyproject,
            tag="fabric-agent:test",
            base_image_url="registry.example/base",
            base_image_tag="release",
            python_version="3.13",
            uv_version="0.8.15",
            allow_root=True,
            sandbox_runtime="openshell",
            agent_version="2.0.0",
            agent_author="Agent Author",
            template_path="Dockerfile.fabric.j2",
            skip_validation=True,
            platforms=["linux/amd64"],
            push=True,
        )

        assert result == "fabric-agent:test"
        assert render_calls == [
            (
                (agent_config_path, pyproject),
                {
                    "base_image_url": "registry.example/base",
                    "base_image_tag": "release",
                    "python_version": "3.13",
                    "uv_version": "0.8.15",
                    "allow_root": True,
                    "sandbox_runtime": "openshell",
                    "agent_version": "2.0.0",
                    "agent_author": "Agent Author",
                    "template_path": "Dockerfile.fabric.j2",
                    "metadata": image_metadata,
                },
            )
        ]
        assert build_calls == [
            {
                "context_dir": tmp_path.resolve(),
                "dockerfile": tmp_path / "Dockerfile.generated",
                "tag": "fabric-agent:test",
                "build_args": {
                    "BASE_IMAGE_URL": "registry.example/base",
                    "BASE_IMAGE_TAG": "release",
                    "PYTHON_VERSION": "3.13",
                },
                "platforms": ["linux/amd64"],
                "push": True,
            }
        ]
        assert not (tmp_path / "Dockerfile.generated").exists()
        assert not (tmp_path / ".dockerignore").exists()

    def test_packages_nested_config_and_skill(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder

        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml", "../skills/review")
        skill = _skill(tmp_path / "skills" / "review")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "fabric-agent"\nversion = "1.0.0"\n')

        monkeypatch.setattr(fabric_validator, "translate_agent_config", lambda config: object())

        async def _plan(config: object, *, base_dir: Path, fabric: Any | None = None) -> object:
            del config, base_dir, fabric
            return {"plan": "ok"}

        def _build(**kwargs: object) -> str:
            dockerfile = kwargs["dockerfile"]
            assert isinstance(dockerfile, Path)
            content = dockerfile.read_text()
            assert "COPY ./ /workspace" in content
            assert "ENV AGENT_CONFIG_PATH=/workspace/configs/agent.yaml" in content
            assert (skill / "SKILL.md").is_file()
            return "fabric-agent:test"

        monkeypatch.setattr(fabric_validator, "plan_fabric_config", _plan)
        monkeypatch.setattr(builder, "docker_build", _build)

        result = builder.build_fabric_agent_image(
            agent_config_path,
            pyproject=pyproject,
            tag="fabric-agent:test",
        )

        assert result == "fabric-agent:test"
        assert not (tmp_path / "Dockerfile.generated").exists()
        assert not (tmp_path / ".dockerignore").exists()

    def test_preserves_user_owned_dockerignore(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        dockerignore = tmp_path / ".dockerignore"
        user_content = "custom-output/\n"
        dockerignore.write_text(user_content)

        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        build_fabric_agent_image(
            agent_config_path,
            tag="fabric-agent:test",
            skip_validation=True,
        )

        assert dockerignore.read_text() == user_content
        assert not (tmp_path / "Dockerfile.generated").exists()

    def test_skips_dockerignore_generation_when_disabled(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        build_fabric_agent_image(
            agent_config_path,
            tag="fabric-agent:test",
            skip_validation=True,
            generate_ignore=False,
        )

        assert not (tmp_path / ".dockerignore").exists()

    def test_cleans_transient_files_when_build_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder
        from nemo_agents_plugin.container import metadata, template

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        def _failed_build(**kwargs: object) -> str:
            del kwargs
            raise RuntimeError("docker build failed")

        monkeypatch.setattr(builder, "docker_build", _failed_build)

        with pytest.raises(RuntimeError, match="docker build failed"):
            builder.build_fabric_agent_image(
                agent_config_path,
                tag="fabric-agent:test",
                skip_validation=True,
            )

        assert not (tmp_path / "Dockerfile.generated").exists()
        assert not (tmp_path / ".dockerignore").exists()

    def test_preserves_preexisting_managed_dockerignore(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image
        from nemo_agents_plugin.container.template import DOCKERIGNORE_SENTINEL

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        dockerignore = tmp_path / ".dockerignore"
        dockerignore.write_text(f"{DOCKERIGNORE_SENTINEL}\n# committed file\n")
        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        build_fabric_agent_image(
            agent_config_path,
            tag="fabric-agent:test",
            skip_validation=True,
        )

        assert dockerignore.exists()
        assert dockerignore.read_text().splitlines()[0] == DOCKERIGNORE_SENTINEL

    def test_refuses_to_overwrite_generated_dockerfile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from nemo_agents_plugin.container import metadata, template
        from nemo_agents_plugin.container.builder import build_fabric_agent_image

        agent_config_path = _write_package_config(tmp_path / "agent.yaml")
        generated = tmp_path / "Dockerfile.generated"
        user_content = "FROM user-owned-image\n"
        generated.write_text(user_content)
        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())
        monkeypatch.setattr(template, "render_fabric_dockerfile", lambda *args, **kwargs: "FROM scratch\n")

        with pytest.raises(typer.Exit):
            build_fabric_agent_image(
                agent_config_path,
                tag="fabric-agent:test",
                skip_validation=True,
            )

        assert generated.read_text() == user_content

    def test_builds_with_user_provided_dockerfile(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import nemo_agents_plugin.container.builder as builder
        import nemo_agents_plugin.container.metadata as metadata
        import nemo_agents_plugin.container.template as template

        agent_config_path = _write_package_config(tmp_path / "configs" / "agent.yaml")
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nname = "fabric-agent"\nversion = "1.0.0"\n')
        dockerfile = tmp_path / "Dockerfile.custom"
        dockerfile.write_text("FROM scratch\n")
        build_calls: list[dict[str, object]] = []

        monkeypatch.setattr(metadata, "extract_agent_metadata", lambda *args, **kwargs: _image_metadata())

        def _unexpected_render(*args: object, **kwargs: object) -> str:
            raise AssertionError(f"unexpected Fabric Dockerfile render: {args}, {kwargs}")

        monkeypatch.setattr(template, "render_fabric_dockerfile", _unexpected_render)

        def _build(**kwargs: object) -> str:
            build_calls.append(kwargs)
            return "fabric-agent:test"

        monkeypatch.setattr(builder, "docker_build", _build)

        result = builder.build_fabric_agent_image(
            agent_config_path,
            pyproject=pyproject,
            dockerfile=dockerfile,
            tag="fabric-agent:test",
            base_image_url="registry.example/base",
            base_image_tag="release",
            python_version="3.13",
            uv_version="0.8.15",
            skip_validation=True,
            platforms=["linux/amd64"],
            push=True,
        )

        assert result == "fabric-agent:test"
        assert build_calls == [
            {
                "context_dir": tmp_path.resolve(),
                "dockerfile": dockerfile,
                "tag": "fabric-agent:test",
                "build_args": {
                    "BASE_IMAGE_URL": "registry.example/base",
                    "BASE_IMAGE_TAG": "release",
                    "PYTHON_VERSION": "3.13",
                },
                "platforms": ["linux/amd64"],
                "push": True,
            }
        ]
        assert "NAT_VERSION" not in build_calls[0]["build_args"]
        assert not (tmp_path / "Dockerfile.generated").exists()
        assert not (tmp_path / ".dockerignore").exists()


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
