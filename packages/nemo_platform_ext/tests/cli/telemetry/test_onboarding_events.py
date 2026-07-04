# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for onboarding_step telemetry emitted from the setup flow.

Each instrumented choke point in ``setup.py`` emits exactly one
``OnboardingStepEvent``: COMPLETED on success, ERROR on failure with the
original exception still propagating. ``emit_event`` is patched at its
definition module so the module-attribute call in ``setup.py`` is intercepted.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from nemo_platform.resources.inference.providers import ProvidersResource
from nemo_platform_ext.cli.commands.setup import (
    _bucket_model_count,
    _create_provider,
    _deploy_demo_agent,
    _run_skill_install,
    _wait_for_models,
)
from nemo_platform_ext.cli.commands.skills.base import Scope, Skill
from nemo_platform_ext.cli.telemetry.events import TaskStatusEnum

SETUP_MOD = "nemo_platform_ext.cli.commands.setup"
EMIT_TARGET = "nemo_platform_ext.cli.telemetry.emit.emit_event"


@pytest.fixture
def spinner_console():
    """Patch setup.console with a mock status spinner context manager."""
    mock_status = MagicMock()
    with patch(f"{SETUP_MOD}.console") as mock_console:
        mock_console.status.return_value.__enter__ = MagicMock(return_value=mock_status)
        mock_console.status.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_console, mock_status


def _providers_client() -> MagicMock:
    client = MagicMock()
    client.inference.providers = MagicMock(spec=ProvidersResource)
    return client


def _skill(name: str) -> Skill:
    return Skill(
        name=name,
        description=f"{name} desc",
        version="0.1",
        content=f"# {name}",
        raw=f"---\nname: {name}\n---\n# {name}",
        source_plugin=None,
    )


class TestCreateProviderTelemetry:
    @patch(EMIT_TARGET)
    def test_success_emits_completed(self, emit):
        client = _providers_client()
        _create_provider(
            client,
            name="openai",
            host_url="https://api.openai.com/v1",
            secret_name="openai-api-key",
            workspace="default",
        )
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "provider_connected"
        assert event.task_status == TaskStatusEnum.COMPLETED
        assert event.provider_type == "openai"

    @patch(EMIT_TARGET)
    def test_failure_emits_error_and_reraises(self, emit):
        client = _providers_client()
        client.inference.providers.create.side_effect = RuntimeError("boom")
        with pytest.raises(RuntimeError):
            _create_provider(
                client,
                name="anthropic",
                host_url="https://api.anthropic.com",
                secret_name="anthropic-api-key",
                workspace="default",
            )
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "provider_connected"
        assert event.task_status == TaskStatusEnum.ERROR
        assert event.provider_type == "anthropic"


class TestWaitForModelsTelemetry:
    @patch(EMIT_TARGET)
    def test_emits_completed_with_bucket(self, emit, spinner_console):
        client = MagicMock()
        models = [MagicMock(model_entity_id=f"default/model-{i}") for i in range(3)]
        client.inference.providers.retrieve.return_value = MagicMock(served_models=models)

        with (
            patch(f"{SETUP_MOD}._pause"),
            patch(f"{SETUP_MOD}.time.monotonic", side_effect=[0, 0, 0, 1]),
        ):
            result = _wait_for_models(client, "nvidia-build", "default", round_seconds=30, max_rounds=1)

        assert result == [f"default/model-{i}" for i in range(3)]
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "models_discovered"
        assert event.task_status == TaskStatusEnum.COMPLETED
        assert event.models_discovered_bucket == "1-5"

    @patch(EMIT_TARGET)
    def test_no_models_emits_bucket_zero(self, emit, spinner_console):
        client = MagicMock()
        client.inference.providers.retrieve.return_value = MagicMock(served_models=[])

        with (
            patch(f"{SETUP_MOD}._pause"),
            patch(f"{SETUP_MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 100]),
        ):
            result = _wait_for_models(client, "nvidia-build", "default", round_seconds=5, max_rounds=1)

        assert result == []
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "models_discovered"
        assert event.task_status == TaskStatusEnum.COMPLETED
        assert event.models_discovered_bucket == "0"


class TestRunSkillInstallTelemetry:
    def _run(self, emit, *, install_raises: bool):
        installer = MagicMock()
        if install_raises:
            installer.install.side_effect = RuntimeError("install failed")
        all_skills = {"alpha": _skill("alpha")}
        with patch(f"{SETUP_MOD}.get_installer", return_value=installer):
            _run_skill_install(
                agents=["codex"],
                scope=Scope.PROJECT,
                skill_names=["alpha"],
                all_skills=all_skills,
                project_root=MagicMock(),
            )

    @patch(EMIT_TARGET)
    def test_success_emits_completed(self, emit):
        self._run(emit, install_raises=False)
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "skills_installed"
        assert event.task_status == TaskStatusEnum.COMPLETED
        assert "codex" in event.skills_target

    @patch(EMIT_TARGET)
    def test_failure_emits_error_and_reraises(self, emit):
        import typer

        with pytest.raises(typer.Exit):
            self._run(emit, install_raises=True)
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "skills_installed"
        assert event.task_status == TaskStatusEnum.ERROR
        assert "codex" in event.skills_target


class TestDeployDemoAgentTelemetry:
    def _responses(self, *, status_sequence):
        create_resp = MagicMock(status_code=200)
        create_resp.raise_for_status = MagicMock()
        deploy_resp = MagicMock(status_code=200)
        deploy_resp.raise_for_status = MagicMock()
        deploy_resp.json.return_value = {"name": "calculator-agent-abc12345"}
        status_resps = []
        for s in status_sequence:
            r = MagicMock(status_code=200)
            r.json.return_value = {"name": "calculator-agent-abc12345", "status": s}
            status_resps.append(r)
        return [create_resp, deploy_resp] + status_resps

    @patch(EMIT_TARGET)
    def test_success_emits_completed_true(self, emit, tmp_path, spinner_console):
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")
        responses = self._responses(status_sequence=["running"])
        with (
            patch(f"{SETUP_MOD}.httpx.get", side_effect=responses[2:]),
            patch(f"{SETUP_MOD}.httpx.post", side_effect=responses[:2]),
            patch(f"{SETUP_MOD}._agent_exists", return_value=False),
            patch(f"{SETUP_MOD}._pause"),
            patch(f"{SETUP_MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 3]),
        ):
            result = _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")
        assert result is True
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "agent_deployed"
        assert event.task_status == TaskStatusEnum.COMPLETED
        assert event.agent_deployed is True

    @patch(EMIT_TARGET)
    def test_failure_emits_error_and_reraises(self, emit, tmp_path, spinner_console):
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")
        create_resp = MagicMock(status_code=500)
        create_resp.raise_for_status = MagicMock(side_effect=RuntimeError("http 500"))
        with (
            patch(f"{SETUP_MOD}.httpx.post", return_value=create_resp),
            patch(f"{SETUP_MOD}._agent_exists", return_value=False),
        ):
            with pytest.raises(RuntimeError):
                _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")
        assert emit.call_count == 1
        event = emit.call_args[0][0]
        assert event.step == "agent_deployed"
        assert event.task_status == TaskStatusEnum.ERROR
        assert event.agent_deployed is False


class TestBucketModelCount:
    @pytest.mark.parametrize(
        ("count", "expected"),
        [
            (0, "0"),
            (1, "1-5"),
            (5, "1-5"),
            (6, "6-20"),
            (20, "6-20"),
            (21, "21-100"),
            (100, "21-100"),
            (101, "101+"),
            (5000, "101+"),
        ],
    )
    def test_buckets(self, count, expected):
        assert _bucket_model_count(count) == expected
