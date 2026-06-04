# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the nemo setup command."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
import typer
from click.exceptions import Exit as ClickExit
from nemo_platform.resources.inference.providers import ProvidersResource
from nemo_platform_ext.cli.commands.services._process import PortConflict
from nemo_platform_ext.cli.commands.setup import (
    _AGENT_API_READINESS_POLL_INTERVAL,
    _AGENT_DEPLOY_POLL_INTERVAL,
    _AGENT_MARKERS,
    _CONTROLLER_HEALTH_RETRY_DELAY,
    _KNOWN_PROVIDERS_BY_NAME,
    _MODEL_DISCOVERY_POLL_INTERVAL,
    _POST_START_REACHABLE_DELAY,
    _POST_START_REACHABLE_RETRIES,
    _PROBE_CONFIGS,
    _SERVICE_STARTUP_POLL_INTERVAL,
    _SERVICE_STARTUP_TIMEOUT_SECONDS,
    KNOWN_PROVIDERS,
    ONBOARDING_PATHS,
    KeyValidationResult,
    _agent_config_path,
    _agents_plugin_available,
    _auto_setup,
    _bootstrap_config_if_missing,
    _check_controller_health,
    _check_ollama_running,
    _check_platform_reachable,
    _check_platform_reachable_with_retries,
    _create_provider,
    _deploy_demo_agent,
    _detect_coding_agents,
    _ensure_port_available_for_start,
    _filter_agents_by_scope,
    _find_project_root,
    _kill_existing_services,
    _last_startup_service,
    _load_persisted_data_dir,
    _load_skills_with_warnings,
    _maybe_deploy_agent,
    _maybe_install_skills,
    _maybe_start_services,
    _parse_csv_flag,
    _print_onboarding,
    _prompt_custom_provider,
    _register_provider_interactive,
    _render_onboarding_card,
    _resolve_provider_for_url,
    _run_interactive_mode,
    _save_data_dir,
    _select_default_model,
    _start_services_background,
    _validate_api_key,
    _verify_platform_health,
    _wait_for_models,
    _wait_for_platform,
    setup_command,
)
from nemo_platform_ext.cli.commands.skills import registry as skills_registry
from nemo_platform_ext.cli.commands.skills.base import Scope, Skill
from nemo_platform_ext.cli.commands.skills.registry import UnsupportedAgentError
from nemo_platform_ext.config.models import (
    Cluster,
    ConfigFile,
    ConfigParams,
    Context,
    ContextDefinition,
)

SETUP_MOD = "nemo_platform_ext.cli.commands.setup"

# ---------------------------------------------------------------------------
# KnownProvider catalog tests
# ---------------------------------------------------------------------------


class TestKnownProviderCatalog:
    def test_catalog_not_empty(self):
        assert len(KNOWN_PROVIDERS) > 0

    def test_all_providers_have_required_fields(self):
        for p in KNOWN_PROVIDERS:
            assert p.name
            assert p.label
            assert p.description
            assert p.host_url

    def test_by_name_lookup_matches_catalog(self):
        for p in KNOWN_PROVIDERS:
            assert _KNOWN_PROVIDERS_BY_NAME[p.name] is p

    def test_ollama_does_not_require_api_key(self):
        ollama = _KNOWN_PROVIDERS_BY_NAME["ollama"]
        assert not ollama.requires_api_key
        assert ollama.env_var is None

    def test_anthropic_has_custom_auth_header(self):
        anthropic = _KNOWN_PROVIDERS_BY_NAME["anthropic"]
        assert anthropic.auth_header_format is not None
        assert "X-Api-Key" in anthropic.auth_header_format
        assert anthropic.default_extra_headers is not None
        assert "anthropic-version" in anthropic.default_extra_headers

    def test_openai_uses_bearer_auth(self):
        openai = _KNOWN_PROVIDERS_BY_NAME["openai"]
        assert openai.auth_header_format is None
        assert openai.requires_api_key

    def test_frozen_dataclass(self):
        p = KNOWN_PROVIDERS[0]
        with pytest.raises(AttributeError):
            p.name = "changed"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class TestResolveProviderForUrl:
    def test_exact_match(self):
        result = _resolve_provider_for_url("https://api.openai.com/v1")
        assert result is not None
        assert result.name == "openai"

    def test_trailing_slash_stripped(self):
        result = _resolve_provider_for_url("https://api.openai.com/v1/")
        assert result is not None
        assert result.name == "openai"

    def test_unknown_url_returns_none(self):
        result = _resolve_provider_for_url("https://my-custom-llm.example.com/v1")
        assert result is None

    def test_each_known_provider_resolves(self):
        for p in KNOWN_PROVIDERS:
            assert _resolve_provider_for_url(p.host_url) is p


# ---------------------------------------------------------------------------
# Platform reachability
# ---------------------------------------------------------------------------


class TestCheckPlatformReachable:
    def test_reachable(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("nemo_platform_ext.cli.commands.setup.httpx.get", return_value=mock_resp):
            assert _check_platform_reachable("http://localhost:8080") is True

    def test_unreachable(self):
        with patch("nemo_platform_ext.cli.commands.setup.httpx.get", side_effect=Exception("conn refused")):
            assert _check_platform_reachable("http://localhost:8080") is False

    def test_non_200_status(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("nemo_platform_ext.cli.commands.setup.httpx.get", return_value=mock_resp):
            assert _check_platform_reachable("http://localhost:8080") is False


# ---------------------------------------------------------------------------
# Platform reachability with retries
# ---------------------------------------------------------------------------


class TestCheckPlatformReachableWithRetries:
    """After startup the health endpoint can flip-flop while controllers initialize."""

    def test_succeeds_on_first_try(self):
        with patch(f"{SETUP_MOD}._check_platform_reachable", return_value=True):
            assert _check_platform_reachable_with_retries("http://localhost:8080") is True

    def test_succeeds_after_transient_failures(self):
        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", side_effect=[False, False, True]),
            patch(f"{SETUP_MOD}._pause") as mock_pause,
        ):
            assert _check_platform_reachable_with_retries("http://localhost:8080", retries=3) is True
        assert mock_pause.call_count == 2

    def test_fails_after_all_retries_exhausted(self):
        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", return_value=False),
            patch(f"{SETUP_MOD}._pause"),
        ):
            assert _check_platform_reachable_with_retries("http://localhost:8080", retries=3) is False

    def test_uses_configured_delay_between_retries(self):
        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", side_effect=[False, True]),
            patch(f"{SETUP_MOD}._pause") as mock_pause,
        ):
            _check_platform_reachable_with_retries("http://localhost:8080", retries=2, delay=4.0)
        mock_pause.assert_called_once_with(4.0)

    def test_no_pause_after_final_failed_attempt(self):
        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", return_value=False),
            patch(f"{SETUP_MOD}._pause") as mock_pause,
        ):
            _check_platform_reachable_with_retries("http://localhost:8080", retries=2)
        assert mock_pause.call_count == 1

    def test_defaults_match_constants(self):
        assert _POST_START_REACHABLE_RETRIES == 6
        assert _POST_START_REACHABLE_DELAY == 2.0


# ---------------------------------------------------------------------------
# Ollama detection
# ---------------------------------------------------------------------------


class TestCheckOllamaRunning:
    def test_ollama_running(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("nemo_platform_ext.cli.commands.setup.httpx.get", return_value=mock_resp):
            assert _check_ollama_running("http://localhost:11434/v1") is True

    def test_ollama_not_running(self):
        with patch("nemo_platform_ext.cli.commands.setup.httpx.get", side_effect=Exception("conn refused")):
            assert _check_ollama_running("http://localhost:11434/v1") is False


# ---------------------------------------------------------------------------
# Shared mock helpers
# ---------------------------------------------------------------------------


def _make_mock_client(*, provider_exists: bool = False, secret_exists: bool = False) -> MagicMock:
    """Build a mock NeMoPlatform client with configurable provider/secret state."""
    client = MagicMock()
    client.inference.providers = MagicMock(spec=ProvidersResource)
    if secret_exists:
        client.secrets.retrieve.return_value = MagicMock()
    else:
        client.secrets.retrieve.side_effect = Exception("not found")
    if provider_exists:
        client.inference.providers.retrieve.return_value = MagicMock()
    else:
        client.inference.providers.retrieve.side_effect = Exception("not found")
    return client


# ---------------------------------------------------------------------------
# Provider creation
# ---------------------------------------------------------------------------


class TestCreateProvider:
    """Tests for _create_provider -- ensures only SDK-supported kwargs are passed."""

    def _make_client(self):
        client = MagicMock()
        client.inference.providers = MagicMock(spec=ProvidersResource)
        return client

    def test_anthropic_provider_kwargs(self):
        """auth_header_format must be mapped to required_extra_headers, not passed raw."""
        client = self._make_client()
        _create_provider(
            client,
            name="anthropic",
            host_url="https://api.anthropic.com",
            secret_name="anthropic-api-key",
            workspace="default",
            auth_header_format="X-Api-Key: {{ auth_secret }}",
            default_extra_headers={"anthropic-version": "2023-06-01"},
        )
        call_kwargs = client.inference.providers.create.call_args.kwargs
        assert "auth_header_format" not in call_kwargs
        assert call_kwargs["required_extra_headers"]["X-Api-Key"] == "{{ auth_secret }}"
        assert call_kwargs["default_extra_headers"] == {"anthropic-version": "2023-06-01"}

    def test_no_auth_header_format_skips_required_extra_headers(self):
        """When auth_header_format is None, required_extra_headers should not be added."""
        client = self._make_client()
        _create_provider(
            client,
            name="openai",
            host_url="https://api.openai.com/v1",
            secret_name="openai-api-key",
            workspace="default",
        )
        call_kwargs = client.inference.providers.create.call_args.kwargs
        assert "auth_header_format" not in call_kwargs
        assert "required_extra_headers" not in call_kwargs

    def test_provider_without_secret(self):
        """Providers without secrets (e.g. Ollama) should omit api_key_secret_name."""
        client = self._make_client()
        _create_provider(
            client,
            name="ollama",
            host_url="http://localhost:11434/v1",
            secret_name=None,
            workspace="default",
        )
        call_kwargs = client.inference.providers.create.call_args.kwargs
        assert "api_key_secret_name" not in call_kwargs


# ---------------------------------------------------------------------------
# Auto setup
# ---------------------------------------------------------------------------

_VALID_KEY_RESULT = KeyValidationResult(passed=True, message="")


@pytest.fixture(autouse=False)
def _bypass_key_validation():
    """Stub out API key validation so tests focused on registration logic are not affected."""
    with patch(
        "nemo_platform_ext.cli.commands.setup._validate_api_key",
        return_value=_VALID_KEY_RESULT,
    ):
        yield


@pytest.mark.usefixtures("_bypass_key_validation")
class TestAutoSetup:
    def test_no_env_vars_returns_false(self):
        client = _make_mock_client()
        with patch.dict("os.environ", {}, clear=True):
            assert _auto_setup(client, "default") is False

    def test_openai_key_creates_provider(self):
        client = _make_mock_client()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        client.secrets.create.assert_called_once()
        client.inference.providers.create.assert_called_once()
        create_kwargs = client.inference.providers.create.call_args
        assert create_kwargs.kwargs["name"] == "openai"
        assert create_kwargs.kwargs["host_url"] == "https://api.openai.com/v1"

    def test_nvidia_key_creates_build_provider(self):
        client = _make_mock_client()
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-test"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        create_kwargs = client.inference.providers.create.call_args
        assert create_kwargs.kwargs["name"] == "nvidia-build"

    def test_nemo_default_key_with_url(self):
        client = _make_mock_client()
        env = {
            "NEMO_DEFAULT_INFERENCE_KEY": "my-key",
            "NEMO_DEFAULT_INFERENCE_BASE_URL": "https://api.openai.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        create_kwargs = client.inference.providers.create.call_args
        assert create_kwargs.kwargs["name"] == "openai"

    def test_nemo_default_key_with_custom_url(self):
        client = _make_mock_client()
        env = {
            "NEMO_DEFAULT_INFERENCE_KEY": "my-key",
            "NEMO_DEFAULT_INFERENCE_BASE_URL": "https://my-custom-llm.example.com/v1",
        }
        with patch.dict("os.environ", env, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        create_kwargs = client.inference.providers.create.call_args
        assert create_kwargs.kwargs["name"] == "my-custom-llm-example-com"
        assert create_kwargs.kwargs["host_url"] == "https://my-custom-llm.example.com/v1"

    def test_existing_provider_updated_not_recreated(self):
        client = _make_mock_client(provider_exists=True, secret_exists=True)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test123"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        client.inference.providers.create.assert_not_called()
        client.inference.providers.update.assert_called_once()

    def test_priority_order(self):
        """NEMO_DEFAULT_INFERENCE_KEY takes priority over OPENAI_API_KEY."""
        client = _make_mock_client()
        env = {
            "NEMO_DEFAULT_INFERENCE_KEY": "nemo-key",
            "NEMO_DEFAULT_INFERENCE_BASE_URL": "https://api.anthropic.com",
            "OPENAI_API_KEY": "sk-test123",
        }
        with patch.dict("os.environ", env, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        create_kwargs = client.inference.providers.create.call_args
        assert create_kwargs.kwargs["name"] == "anthropic"

    def test_anthropic_auto_setup_maps_auth_header(self):
        """Auto-setup with ANTHROPIC_API_KEY must map auth_header_format to required_extra_headers."""
        client = _make_mock_client()
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        call_kwargs = client.inference.providers.create.call_args.kwargs
        assert call_kwargs["name"] == "anthropic"
        assert "auth_header_format" not in call_kwargs
        assert "X-Api-Key" in call_kwargs["required_extra_headers"]


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------


class TestDefaultModelConfig:
    def test_context_definition_has_default_model(self):
        ctx = ContextDefinition(name="test", cluster="c", user="u")
        assert ctx.default_model is None

        ctx2 = ContextDefinition(name="test", cluster="c", user="u", default_model="my-model")
        assert ctx2.default_model == "my-model"

    def test_config_params_accepts_default_model(self):
        params: ConfigParams = {"default_model": "workspace/openai-gpt-4o"}
        assert params["default_model"] == "workspace/openai-gpt-4o"

    def test_ensure_context_applies_default_model(self):
        config_file = ConfigFile(
            current_context="test",
            clusters=[{"name": "test-cluster", "base_url": "http://localhost:8080"}],
            users=[{"name": "test-user", "type": "no-auth"}],
            contexts=[{"name": "test", "cluster": "test-cluster", "user": "test-user"}],
        )
        params: ConfigParams = {"default_model": "workspace/my-model"}
        _, _, ctx_def = config_file.ensure_context("test", params)
        assert ctx_def.default_model == "workspace/my-model"

    def test_context_has_default_model(self):
        ctx = Context(
            context_name="test",
            cluster=Cluster(name="c", base_url="http://localhost:8080"),
            workspace="default",
            default_model="workspace/gpt-4o",
            preferences={},
        )
        assert ctx.default_model == "workspace/gpt-4o"


# ---------------------------------------------------------------------------
# Service startup helpers
# ---------------------------------------------------------------------------


class TestKillExistingServices:
    """``_kill_existing_services`` delegates to ``_process.stop_instance``."""

    def test_delegates_to_stop_instance(self):
        with patch(f"{SETUP_MOD}.stop_instance") as mock_stop:
            mock_stop.return_value = MagicMock(stopped_pids=[])
            _kill_existing_services("http://localhost:8080")
        mock_stop.assert_called_once()
        _, kwargs = mock_stop.call_args
        assert kwargs["timeout"] == 2.0
        assert kwargs["force"] is True


@pytest.fixture
def maybe_start_preflight_mocks():
    """Shared mocks for ``_maybe_start_services`` preflight tests."""
    with (
        patch(f"{SETUP_MOD}._check_platform_reachable", return_value=False),
        patch(f"{SETUP_MOD}.importlib.util.find_spec", return_value=MagicMock()),
        patch(f"{SETUP_MOD}._start_services_background") as mock_start,
        patch(f"{SETUP_MOD}.prompt_choice", return_value="yes"),
        patch(f"{SETUP_MOD}._prompt_data_dir", return_value="/tmp/data"),
    ):
        yield mock_start


class TestMaybeStartServices:
    def test_skips_when_running_and_start_not_requested(self):
        with patch(f"{SETUP_MOD}._check_platform_reachable", return_value=True):
            _maybe_start_services("http://localhost:8080", auto=False, start_services=None)

    def test_skips_when_running_and_explicitly_false(self):
        with patch(f"{SETUP_MOD}._check_platform_reachable", return_value=True):
            _maybe_start_services("http://localhost:8080", auto=False, start_services=False)

    def test_restarts_when_running_and_start_services_true(self):
        reachable_calls = [True, True, False, True]

        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", side_effect=reachable_calls),
            patch(f"{SETUP_MOD}._kill_existing_services") as mock_kill,
            patch(f"{SETUP_MOD}._start_services_background") as mock_start,
            patch(f"{SETUP_MOD}._wait_for_platform", return_value=True),
            patch(f"{SETUP_MOD}._prompt_data_dir", return_value="/tmp/test-data") as mock_db_prompt,
            patch(f"{SETUP_MOD}.check_port_available_for_start", return_value=None),
            patch(f"{SETUP_MOD}._ensure_port_available_for_start", wraps=_ensure_port_available_for_start) as mock_port,
            patch(f"{SETUP_MOD}._pause"),
        ):
            mock_start.return_value = MagicMock(pid=999)
            _maybe_start_services("http://localhost:8080", auto=False, start_services=True)
        mock_kill.assert_called_once()
        mock_port.assert_called_once()
        mock_start.assert_called_once_with("http://localhost:8080", data_dir="/tmp/test-data")
        mock_db_prompt.assert_called_once()

    def test_restarts_exits_when_port_still_occupied_after_kill(self, capsys):
        """Port preflight runs after kill/wait and blocks spawn when the port stays busy."""
        reachable_calls = [True, True, False, True]
        conflict = PortConflict(kind="foreign", port=8080)

        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", side_effect=reachable_calls),
            patch(f"{SETUP_MOD}._kill_existing_services") as mock_kill,
            patch(f"{SETUP_MOD}._start_services_background") as mock_start,
            patch(f"{SETUP_MOD}.check_port_available_for_start", return_value=conflict),
            patch(f"{SETUP_MOD}._prompt_data_dir", return_value="/tmp/test-data"),
            patch(f"{SETUP_MOD}._pause"),
            pytest.raises(ClickExit),
        ):
            _maybe_start_services("http://localhost:8080", auto=False, start_services=True)
        mock_kill.assert_called_once()
        mock_start.assert_not_called()
        captured = capsys.readouterr()
        assert "already in use" in captured.err
        assert "services.log" not in captured.err

    def test_exits_early_when_services_extra_missing(self, maybe_start_preflight_mocks, capsys):
        """Preflight aborts with install hint before spawning a subprocess."""
        with (
            patch(f"{SETUP_MOD}.importlib.util.find_spec", return_value=None),
            pytest.raises(ClickExit),
        ):
            _maybe_start_services("http://localhost:8080", auto=False, start_services=True)
        maybe_start_preflight_mocks.assert_not_called()
        captured = capsys.readouterr()
        assert "nemo-platform[all]" in captured.err

    def test_exits_early_when_port_occupied(self, maybe_start_preflight_mocks, capsys):
        """Preflight aborts with port hint on stderr before spawning a subprocess."""
        conflict = PortConflict(kind="foreign", port=8080)
        with (
            patch(f"{SETUP_MOD}.check_port_available_for_start", return_value=conflict),
            pytest.raises(ClickExit),
        ):
            _maybe_start_services("http://localhost:8080", auto=False, start_services=True)
        maybe_start_preflight_mocks.assert_not_called()
        captured = capsys.readouterr()
        assert "already in use" in captured.err
        assert "lsof" in captured.err
        assert "services.log" not in captured.err

    def test_allows_start_when_port_free(self, maybe_start_preflight_mocks):
        with (
            patch(f"{SETUP_MOD}.check_port_available_for_start", return_value=None),
            patch(f"{SETUP_MOD}._wait_for_platform", return_value=True),
            patch(f"{SETUP_MOD}._pause"),
        ):
            maybe_start_preflight_mocks.return_value = MagicMock(pid=999)
            _maybe_start_services("http://localhost:8080", auto=False, start_services=True)
        maybe_start_preflight_mocks.assert_called_once()


class TestLocalDataDirHelpers:
    """Tests for the XDG-default data-dir helpers used by `nemo setup`."""

    def test_load_persisted_returns_none_when_no_config_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("NMP_CONFIG_FILE", str(tmp_path / "missing.yaml"))
        assert _load_persisted_data_dir() is None

    def test_save_then_load_roundtrips_data_dir(self, tmp_path, monkeypatch):
        config_path = tmp_path / "config.yaml"
        monkeypatch.setenv("NMP_CONFIG_FILE", str(config_path))
        _save_data_dir("/custom/data/dir")
        assert _load_persisted_data_dir() == "/custom/data/dir"

    def test_start_services_background_forwards_data_dir(self):
        """The setup.py wrapper should pass *data_dir* through to the shared
        process lifecycle module unchanged. The actual ``NMP_DATA_DIR``
        environment injection lives in ``services._process`` and is covered
        by its own tests."""
        with patch(f"{SETUP_MOD}.start_background") as mock_start:
            mock_start.return_value = MagicMock(pid=42)
            _start_services_background("http://localhost:9090", data_dir="/chosen/data/dir")
        mock_start.assert_called_once()
        _, kwargs = mock_start.call_args
        assert kwargs["data_dir"] == "/chosen/data/dir"
        assert kwargs["port"] == 9090

    def test_auto_mode_skips_prompt_and_uses_persisted(self, tmp_path, monkeypatch):
        """`--auto` must not prompt but should still honor any persisted data dir."""
        config_path = tmp_path / "config.yaml"
        monkeypatch.setenv("NMP_CONFIG_FILE", str(config_path))
        _save_data_dir("/persisted/from/setup")

        with (
            patch(f"{SETUP_MOD}._check_platform_reachable", return_value=False),
            patch(f"{SETUP_MOD}._kill_existing_services"),
            patch(f"{SETUP_MOD}._start_services_background") as mock_start,
            patch(f"{SETUP_MOD}._wait_for_platform", return_value=True),
            patch(f"{SETUP_MOD}._prompt_data_dir") as mock_prompt,
            patch(f"{SETUP_MOD}._pause"),
        ):
            mock_start.return_value = MagicMock(pid=999)
            _maybe_start_services("http://localhost:8080", auto=True, start_services=True)
        mock_prompt.assert_not_called()
        mock_start.assert_called_once_with("http://localhost:8080", data_dir="/persisted/from/setup")

    def test_bootstrap_seeds_cluster_when_only_data_dir_persisted(self, tmp_path, monkeypatch):
        """Reproduces the user-reported crash where ``_prompt_data_dir`` writes a
        partial config (just ``local_services.data_dir``) before bootstrap runs.

        ``_bootstrap_config_if_missing`` used to short-circuit on
        ``config_path.exists()``, leaving the file without any cluster. Later
        steps (`_save_default_model` → ``Config.write`` → ``ensure_context``)
        then raised ``Cluster 'default-cluster' does not exist and no base_url
        provided to create it!`` when the user picked a default model.

        After the fix, bootstrap recognizes a partial config (clusters empty)
        and seeds the cluster + context while preserving the data dir.
        """
        config_path = tmp_path / "config.yaml"
        monkeypatch.setenv("NMP_CONFIG_FILE", str(config_path))

        # Simulate the partial-config state that ``_prompt_data_dir`` leaves
        # behind when run on a fresh install.
        _save_data_dir("/chosen/data/dir")
        assert config_path.exists()
        from nemo_platform_ext.config.config import Config

        before = Config.load(config_path=config_path).get_config_file()
        assert before.clusters == []  # exactly the user's broken state
        assert before.local_services is not None
        assert before.local_services.data_dir == "/chosen/data/dir"

        # Bootstrap should now seed the cluster (was a no-op pre-fix).
        _bootstrap_config_if_missing("http://localhost:8080", "default")

        after = Config.load(config_path=config_path).get_config_file()
        assert len(after.clusters) == 1
        assert str(after.clusters[0].base_url).rstrip("/") == "http://localhost:8080"
        # Data dir was preserved across the bootstrap write.
        assert after.local_services is not None
        assert after.local_services.data_dir == "/chosen/data/dir"

    def test_bootstrap_is_noop_when_cluster_already_seeded(self, tmp_path, monkeypatch):
        """Idempotency check: bootstrap should not rewrite an already-seeded config."""
        config_path = tmp_path / "config.yaml"
        monkeypatch.setenv("NMP_CONFIG_FILE", str(config_path))

        # First seed.
        _bootstrap_config_if_missing("http://localhost:8080", "default")
        mtime_before = config_path.stat().st_mtime_ns

        # Second call should be a no-op (no rewrite, same mtime).
        _bootstrap_config_if_missing("http://other:9090", "other")
        mtime_after = config_path.stat().st_mtime_ns
        assert mtime_after == mtime_before

        from nemo_platform_ext.config.config import Config

        after = Config.load(config_path=config_path).get_config_file()
        # Original cluster URL preserved (not overwritten by the second call).
        assert str(after.clusters[0].base_url).rstrip("/") == "http://localhost:8080"


class TestMaybeDeployAgentPluginCheck:
    def test_skips_without_prompting_when_plugin_missing(self):
        """When plugin is not available, user should never be prompted."""
        with (
            patch(f"{SETUP_MOD}._agents_plugin_available", return_value=False),
            patch(f"{SETUP_MOD}.prompt_choice") as mock_prompt,
        ):
            _maybe_deploy_agent("http://localhost:8080", "default", auto=False, deploy_agent=None)
        mock_prompt.assert_not_called()

    def test_prompts_when_plugin_available(self):
        with (
            patch(f"{SETUP_MOD}._agents_plugin_available", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="no") as mock_prompt,
        ):
            _maybe_deploy_agent("http://localhost:8080", "default", auto=False, deploy_agent=None)
        mock_prompt.assert_called_once()


# ---------------------------------------------------------------------------
# Skills installation helpers
# ---------------------------------------------------------------------------


class TestDetectCodingAgents:
    def test_detects_cursor_directory(self, tmp_path):
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".git").mkdir()
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=tmp_path):
            detected = _detect_coding_agents()
        agent_names = [name for _, name in detected]
        assert "cursor" in agent_names

    def test_detects_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").touch()
        (tmp_path / ".git").mkdir()
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=tmp_path):
            detected = _detect_coding_agents()
        agent_names = [name for _, name in detected]
        assert "codex" in agent_names

    def test_detects_multiple_agents(self, tmp_path):
        (tmp_path / "AGENTS.md").touch()
        (tmp_path / ".cursor").mkdir()
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".git").mkdir()
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=tmp_path):
            detected = _detect_coding_agents()
        agent_names = [name for _, name in detected]
        assert "codex" in agent_names
        assert "cursor" in agent_names
        assert "claude" in agent_names

    def test_returns_empty_when_none_found(self, tmp_path):
        (tmp_path / ".git").mkdir()
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=tmp_path):
            detected = _detect_coding_agents()
        assert detected == []


class TestAgentMarkers:
    def test_all_markers_have_agent_names(self):
        for marker, agent_name in _AGENT_MARKERS:
            assert marker
            assert agent_name


# ---------------------------------------------------------------------------
# Skills installation helpers
# ---------------------------------------------------------------------------


class TestParseCsvFlag:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (None, None),
            ("codex", ["codex"]),
            ("codex,cursor,claude", ["codex", "cursor", "claude"]),
            (" codex , cursor ", ["codex", "cursor"]),
            ("", None),
            (",,,", None),
        ],
    )
    def test_parse(self, raw, expected):
        assert _parse_csv_flag(raw) == expected


class TestFilterAgentsByScope:
    def test_project_scope_keeps_all_supported_agents(self):
        kept, skipped = _filter_agents_by_scope(["claude", "cursor", "codex"], Scope.PROJECT)
        assert set(kept) == {"claude", "cursor", "codex"}
        assert skipped == []

    def test_user_scope_skips_cursor(self):
        # Cursor only supports PROJECT scope; should be filtered out at USER scope.
        kept, skipped = _filter_agents_by_scope(["claude", "cursor", "codex"], Scope.USER)
        assert "cursor" not in kept
        assert {"claude", "codex"}.issubset(set(kept))
        assert any(name == "cursor" for name, _ in skipped)
        cursor_reason = next(reason for name, reason in skipped if name == "cursor")
        assert "user" in cursor_reason

    def test_user_scope_keeps_codex_and_claude(self):
        kept, _ = _filter_agents_by_scope(["claude", "codex"], Scope.USER)
        assert set(kept) == {"claude", "codex"}


class TestLoadSkillsWithWarnings:
    def test_captures_plugin_warnings(self):
        # Stub load_skills so it emits a warning via the registry logger; the
        # capture handler should pick it up and return it as a structured message.
        def _stub() -> dict:
            skills_registry.logger.warning("Skipping plugin 'fake': boom")
            return {}

        with patch("nemo_platform_ext.cli.commands.setup.load_skills", side_effect=_stub):
            skills, warnings = _load_skills_with_warnings()
        assert skills == {}
        assert any("Skipping plugin 'fake'" in msg for msg in warnings)

    def test_handler_cleaned_up_on_exception(self):
        handler_count_before = len(skills_registry.logger.handlers)

        def _boom() -> dict:
            raise RuntimeError("kaboom")

        with patch("nemo_platform_ext.cli.commands.setup.load_skills", side_effect=_boom):
            with pytest.raises(RuntimeError):
                _load_skills_with_warnings()
        # Even on exception, the capture handler is removed.
        assert len(skills_registry.logger.handlers) == handler_count_before

    def test_warnings_captured_even_when_logger_level_above_warning(self):
        """If an upstream caller raised the registry logger to ERROR, plugin
        warnings should still reach the preview."""

        def _stub() -> dict:
            skills_registry.logger.warning("Skipping plugin 'quiet': nothing here")
            return {}

        original = skills_registry.logger.level
        skills_registry.logger.setLevel(logging.ERROR)
        try:
            with patch("nemo_platform_ext.cli.commands.setup.load_skills", side_effect=_stub):
                _, warnings = _load_skills_with_warnings()
            assert any("Skipping plugin 'quiet'" in m for m in warnings)
            # Logger level is restored to ERROR after the call.
            assert skills_registry.logger.level == logging.ERROR
        finally:
            skills_registry.logger.setLevel(original)


class TestMaybeInstallSkills:
    @staticmethod
    def _skill(name: str, plugin: str | None = None) -> Skill:
        return Skill(
            name=name,
            description=f"{name} desc",
            version="0.1",
            content=f"# {name}",
            raw=f"---\nname: {name}\n---\n# {name}",
            source_plugin=plugin,
        )

    def _patched_install(self, tmp_path, **call_kwargs):
        """Run _maybe_install_skills with detection and project root pinned, capturing installer calls."""
        # alpha is built-in (source_plugin=None → "nemo-platform"); beta comes
        # from a plugin so source filtering can be exercised independently.
        skills = {
            "alpha": self._skill("alpha"),
            "beta": self._skill("beta", plugin="example-plugin"),
        }

        recorded_calls: list[tuple[str, Scope, dict]] = []

        class _StubInstaller:
            def __init__(self, name: str, scopes: list[Scope]):
                self.name = name
                self.supported_scopes = scopes

            def install(self, scope, project_root, sk):
                recorded_calls.append((self.name, scope, sk))
                return []

            def get_install_path(self, scope, project_root, skill_name):
                return project_root / "stub" / skill_name

        installers = {
            "codex": _StubInstaller("codex", [Scope.PROJECT, Scope.USER]),
            "cursor": _StubInstaller("cursor", [Scope.PROJECT]),
            "claude": _StubInstaller("claude", [Scope.PROJECT, Scope.USER]),
        }

        with (
            patch(
                "nemo_platform_ext.cli.commands.setup._detect_coding_agents",
                return_value=[("AGENTS.md", "codex"), (".cursor", "cursor"), (".claude", "claude")],
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._load_skills_with_warnings",
                return_value=(skills, []),
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup.get_installer",
                side_effect=lambda name: installers[name],
            ),
        ):
            _maybe_install_skills(**call_kwargs)
        return recorded_calls

    @pytest.mark.parametrize(
        "call_kwargs",
        [
            # --install-skills=False is an explicit opt-out
            {"install_skills": False},
            # --install-skills=None (unset) is a noop without an explicit opt-in
            {"install_skills": None},
            # Filter flags alone don't opt in; --install-skills is the master switch.
            {"install_skills": None, "skills_scope": Scope.USER},
            {"install_skills": None, "skills_agents": ["codex"]},
            {"install_skills": None, "skills_from": ["nemo-platform"]},
        ],
        ids=[
            "install_skills_false",
            "install_skills_none",
            "skills_scope_only",
            "skills_agents_only",
            "skills_from_only",
        ],
    )
    def test_noop_when_install_skills_not_true(self, tmp_path, call_kwargs):
        calls = self._patched_install(tmp_path, auto=True, **call_kwargs)
        assert calls == []

    def test_auto_with_install_skills_true_installs_all_detected_at_project(self, tmp_path):
        calls = self._patched_install(tmp_path, auto=True, install_skills=True)
        installed_agents = {name for name, _, _ in calls}
        assert installed_agents == {"codex", "cursor", "claude"}
        for _name, scope, _sk in calls:
            assert scope == Scope.PROJECT

    def test_skills_agents_flag_filters_install_loop(self, tmp_path):
        calls = self._patched_install(
            tmp_path,
            auto=True,
            install_skills=True,
            skills_agents=["codex"],
        )
        assert {name for name, _, _ in calls} == {"codex"}

    def test_skills_scope_user_filters_out_cursor(self, tmp_path):
        calls = self._patched_install(
            tmp_path,
            auto=True,
            install_skills=True,
            skills_scope=Scope.USER,
        )
        installed_agents = {name for name, _, _ in calls}
        # Cursor doesn't support USER scope; should be skipped, not installed.
        assert "cursor" not in installed_agents
        assert {"codex", "claude"}.issubset(installed_agents)
        for _name, scope, _sk in calls:
            assert scope == Scope.USER

    def test_skills_from_builtin_only(self, tmp_path):
        """--skills-from nemo-platform installs only built-in skills."""
        calls = self._patched_install(
            tmp_path,
            auto=True,
            install_skills=True,
            skills_from=["nemo-platform"],
        )
        for _name, _scope, sk in calls:
            assert set(sk.keys()) == {"alpha"}

    def test_skills_from_plugin_only(self, tmp_path):
        """--skills-from example-plugin installs only plugin-provided skills."""
        calls = self._patched_install(
            tmp_path,
            auto=True,
            install_skills=True,
            skills_from=["example-plugin"],
        )
        for _name, _scope, sk in calls:
            assert set(sk.keys()) == {"beta"}

    def test_skills_from_multiple_sources_unions(self, tmp_path):
        """Passing several sources installs the union of their skills."""
        calls = self._patched_install(
            tmp_path,
            auto=True,
            install_skills=True,
            skills_from=["nemo-platform", "example-plugin"],
        )
        for _name, _scope, sk in calls:
            assert set(sk.keys()) == {"alpha", "beta"}

    def test_unknown_skills_from_raises_bad_parameter(self, tmp_path):
        """A typo in --skills-from fails fast with a clear typer.BadParameter."""
        with pytest.raises(typer.BadParameter) as exc_info:
            self._patched_install(
                tmp_path,
                auto=True,
                install_skills=True,
                skills_from=["does-not-exist"],
            )
        assert "Unknown skill source" in str(exc_info.value.message) or "Unknown skill source" in str(exc_info.value)

    def test_all_install_failures_raise_exit(self, tmp_path):
        """If every agent's install raises, --auto should exit non-zero so CI catches it."""
        skills = {"alpha": self._skill("alpha")}

        class _AlwaysFailInstaller:
            name = "x"
            supported_scopes = [Scope.PROJECT, Scope.USER]

            def install(self, scope, project_root, sk):
                raise RuntimeError("disk full")

            def get_install_path(self, scope, project_root, skill_name):
                return project_root / "stub" / skill_name

        failing = _AlwaysFailInstaller()
        installers = {"codex": failing, "claude": failing}

        with (
            patch(
                "nemo_platform_ext.cli.commands.setup._detect_coding_agents",
                return_value=[("AGENTS.md", "codex"), (".claude", "claude")],
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._load_skills_with_warnings",
                return_value=(skills, []),
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup.get_installer",
                side_effect=lambda name: installers[name],
            ),
            pytest.raises(typer.Exit) as exc_info,
        ):
            _maybe_install_skills(auto=True, install_skills=True)
        assert exc_info.value.exit_code == 1

    def test_skills_agents_overrides_empty_detection(self, tmp_path):
        """An explicit --skills-agents must install even when no markers exist."""
        skills = {"alpha": self._skill("alpha")}
        recorded: list[tuple[str, Scope, dict]] = []

        class _StubInstaller:
            supported_scopes = [Scope.PROJECT, Scope.USER]

            def __init__(self, name: str):
                self.name = name

            def install(self, scope, project_root, sk):
                recorded.append((self.name, scope, sk))
                return []

            def get_install_path(self, scope, project_root, skill_name):
                return project_root / "stub" / skill_name

        with (
            patch(
                "nemo_platform_ext.cli.commands.setup._detect_coding_agents",
                return_value=[],
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._load_skills_with_warnings",
                return_value=(skills, []),
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup.get_installer",
                side_effect=lambda name: _StubInstaller(name),
            ),
        ):
            _maybe_install_skills(
                auto=True,
                install_skills=True,
                skills_agents=["codex"],
            )

        assert [name for name, _, _ in recorded] == ["codex"]

    def test_unknown_skills_agents_raises_unsupported_agent(self, tmp_path):
        """Typos in --skills-agents fail fast via UnsupportedAgentError (before any install work)."""
        # Don't even need to patch detection — validation happens up-front.
        with pytest.raises(UnsupportedAgentError):
            _maybe_install_skills(
                auto=True,
                install_skills=True,
                skills_agents=["copex"],  # typo
            )

    def test_partial_install_failure_does_not_raise(self, tmp_path):
        """Mixed success/failure shouldn't fail the run; only total failure should."""
        skills = {"alpha": self._skill("alpha")}

        class _SuccessInstaller:
            supported_scopes = [Scope.PROJECT, Scope.USER]

            def install(self, scope, project_root, sk):
                return []

            def get_install_path(self, scope, project_root, skill_name):
                return project_root / "stub" / skill_name

        class _FailInstaller:
            supported_scopes = [Scope.PROJECT, Scope.USER]

            def install(self, scope, project_root, sk):
                raise RuntimeError("nope")

            def get_install_path(self, scope, project_root, skill_name):
                return project_root / "stub" / skill_name

        installers = {"codex": _SuccessInstaller(), "claude": _FailInstaller()}

        with (
            patch(
                "nemo_platform_ext.cli.commands.setup._detect_coding_agents",
                return_value=[("AGENTS.md", "codex"), (".claude", "claude")],
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._load_skills_with_warnings",
                return_value=(skills, []),
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup._find_project_root",
                return_value=tmp_path,
            ),
            patch(
                "nemo_platform_ext.cli.commands.setup.get_installer",
                side_effect=lambda name: installers[name],
            ),
        ):
            # Should NOT raise — one agent succeeded.
            _maybe_install_skills(auto=True, install_skills=True)


# ---------------------------------------------------------------------------
# Agent deployment helpers
# ---------------------------------------------------------------------------


class TestAgentsPluginAvailable:
    def test_returns_true_when_importable(self):
        with patch("nemo_platform_ext.cli.commands.setup.importlib.util.find_spec", return_value=MagicMock()):
            assert _agents_plugin_available() is True

    def test_returns_false_when_missing(self):
        def side_effect(name):
            if name == "nemo_agents_plugin":
                return None
            return MagicMock()

        with patch("nemo_platform_ext.cli.commands.setup.importlib.util.find_spec", side_effect=side_effect):
            assert _agents_plugin_available() is False


class TestFindProjectRoot:
    def test_finds_git_root(self, tmp_path):
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "a" / "b"
        subdir.mkdir(parents=True)
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=subdir):
            root = _find_project_root()
        assert root == tmp_path

    def test_falls_back_to_cwd(self, tmp_path):
        with patch("nemo_platform_ext.cli.commands.setup.Path.cwd", return_value=tmp_path):
            root = _find_project_root()
        assert root == tmp_path


# ---------------------------------------------------------------------------
# Provider idempotency
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_bypass_key_validation")
class TestProviderIdempotency:
    """Test that setup correctly upserts secrets and providers on re-runs.

    The bug: when a provider already exists but the secret is new (or its
    value has changed), setup skips the provider entirely and never
    re-associates the secret.  Model discovery then fails.
    """

    # -- interactive path --

    def test_existing_secret_gets_updated_with_new_value(self):
        """When the secret already exists, its value should be updated."""
        client = _make_mock_client(secret_exists=True, provider_exists=False)
        _register_provider_interactive(
            client,
            provider_name="nvidia-build",
            host_url="https://integrate.api.nvidia.com",
            api_key="new-key-value",
            workspace="default",
        )
        client.secrets.update.assert_called_once_with(
            "nvidia-build-api-key", value="new-key-value", workspace="default"
        )
        client.secrets.create.assert_not_called()
        client.inference.providers.create.assert_called_once()
        client.inference.providers.update.assert_not_called()

    def test_existing_provider_gets_updated_with_secret(self):
        """When the provider exists, it should be updated to point at the secret."""
        client = _make_mock_client(secret_exists=False, provider_exists=True)
        _register_provider_interactive(
            client,
            provider_name="nvidia-build",
            host_url="https://integrate.api.nvidia.com",
            api_key="my-key",
            workspace="default",
        )
        client.secrets.create.assert_called_once_with(name="nvidia-build-api-key", value="my-key", workspace="default")
        client.secrets.update.assert_not_called()
        client.inference.providers.update.assert_called_once()
        call_kwargs = client.inference.providers.update.call_args.kwargs
        assert call_kwargs["api_key_secret_name"] == "nvidia-build-api-key"
        assert call_kwargs["host_url"] == "https://integrate.api.nvidia.com"
        client.inference.providers.create.assert_not_called()

    def test_fresh_install_creates_both(self):
        """When neither exists, both secret and provider are created (regression guard)."""
        client = _make_mock_client(secret_exists=False, provider_exists=False)
        _register_provider_interactive(
            client,
            provider_name="openai",
            host_url="https://api.openai.com/v1",
            api_key="sk-test",
            workspace="default",
        )
        client.secrets.create.assert_called_once()
        client.inference.providers.create.assert_called_once()
        client.secrets.update.assert_not_called()
        client.inference.providers.update.assert_not_called()

    def test_existing_provider_updated_with_extra_headers(self):
        """Provider update passes through default_extra_headers (auth_header_format is create-only)."""
        client = _make_mock_client(secret_exists=False, provider_exists=True)
        _register_provider_interactive(
            client,
            provider_name="anthropic",
            host_url="https://api.anthropic.com",
            api_key="sk-ant-test",
            workspace="default",
            auth_header_format="X-Api-Key: {{ auth_secret }}",
            default_extra_headers={"anthropic-version": "2023-06-01"},
        )
        call_kwargs = client.inference.providers.update.call_args.kwargs
        assert "auth_header_format" not in call_kwargs
        assert call_kwargs["default_extra_headers"] == {"anthropic-version": "2023-06-01"}

    # -- auto path --

    def test_auto_setup_updates_existing_provider_secret_binding(self):
        """In auto mode, existing provider should be updated with the secret."""
        client = _make_mock_client(provider_exists=True, secret_exists=False)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-new-key"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        client.secrets.create.assert_called_once()
        client.inference.providers.update.assert_called_once()
        call_kwargs = client.inference.providers.update.call_args.kwargs
        assert call_kwargs["api_key_secret_name"] == "openai-api-key"

    def test_auto_setup_updates_existing_secret_value(self):
        """In auto mode, existing secret should be updated with the new key value."""
        client = _make_mock_client(provider_exists=True, secret_exists=True)
        with patch.dict("os.environ", {"NVIDIA_API_KEY": "nvapi-new"}, clear=True):
            result = _auto_setup(client, "default")
        assert result is True
        client.secrets.update.assert_called_once_with("nvidia-build-api-key", value="nvapi-new", workspace="default")
        client.secrets.create.assert_not_called()


# ---------------------------------------------------------------------------
# Interactive setup regression — provider sync timeout vs model picker
# ---------------------------------------------------------------------------


class TestInteractiveDefaultModelSelection:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_skips_default_model_picker_when_new_provider_has_no_models(self):
        """When the new provider is still syncing, setup should not show a misleading picker."""
        client = MagicMock()
        cli_context = MagicMock()

        with (
            patch(
                f"{self._MOD}._interactive_collect_provider",
                return_value=("my-ollama-custom", "http://localhost:11434/v1", "ollama", None, None),
            ),
            patch(f"{self._MOD}._register_provider_interactive"),
            patch(f"{self._MOD}._wait_for_models", return_value=[]),
            patch(f"{self._MOD}._select_default_model") as mock_select_default_model,
            patch(f"{self._MOD}._save_default_model"),
            patch(f"{self._MOD}._maybe_install_skills"),
            patch(f"{self._MOD}._maybe_deploy_agent"),
            patch(f"{self._MOD}._print_onboarding"),
            patch(f"{self._MOD}.console") as mock_console,
        ):
            _run_interactive_mode(
                cli_context,
                client,
                "default",
                "http://localhost:8080",
                install_skills=False,
                deploy_agent=False,
            )

        mock_select_default_model.assert_not_called()
        printed_lines = [call.args[0] for call in mock_console.print.call_args_list if call.args]
        assert any("No models discovered yet (provider may still be syncing)" in line for line in printed_lines)
        assert any("Step 5: Choose default model" in line for line in printed_lines)
        assert any("No default model set for this provider yet." in line for line in printed_lines)
        assert any("Run [cyan]nemo setup[/cyan] again after models sync" in line for line in printed_lines)

    def test_warns_when_only_existing_provider_models_are_available(self):
        """If other providers have models, explain that the new provider is not yet represented."""
        client = MagicMock()
        cli_context = MagicMock()

        with (
            patch(
                f"{self._MOD}._interactive_collect_provider",
                return_value=("my-ollama-custom", "http://localhost:11434/v1", "ollama", None, None),
            ),
            patch(f"{self._MOD}._register_provider_interactive"),
            patch(f"{self._MOD}._wait_for_models", return_value=[]),
            patch(
                f"{self._MOD}._get_all_model_choices",
                return_value=[
                    (
                        "default/meta-llama-3-1-8b-instruct",
                        "meta-llama-3-1-8b-instruct (nvidia-build)",
                    )
                ],
            ),
            patch(f"{self._MOD}._select_default_model") as mock_select_default_model,
            patch(f"{self._MOD}._save_default_model"),
            patch(f"{self._MOD}._maybe_install_skills"),
            patch(f"{self._MOD}._maybe_deploy_agent"),
            patch(f"{self._MOD}._print_onboarding"),
            patch(f"{self._MOD}.console") as mock_console,
        ):
            _run_interactive_mode(
                cli_context,
                client,
                "default",
                "http://localhost:8080",
                install_skills=False,
                deploy_agent=False,
            )

        mock_select_default_model.assert_not_called()
        printed_lines = [call.args[0] for call in mock_console.print.call_args_list if call.args]
        assert any(
            "Models from existing providers are available, but not from 'my-ollama-custom' yet." in line
            for line in printed_lines
        )

    def test_picker_labels_include_provider_names(self):
        """Default model choices should show which provider each model comes from."""
        client = MagicMock()
        provider_a = MagicMock()
        provider_a.name = "nvidia-build"
        provider_a.served_models = [
            MagicMock(model_entity_id="default/meta-llama-3-1-8b-instruct"),
        ]
        provider_b = MagicMock()
        provider_b.name = "my-ollama-custom"
        provider_b.served_models = [
            MagicMock(model_entity_id="default/qwen2.5:1.5b"),
        ]
        client.inference.providers.list.return_value = MagicMock(data=[provider_a, provider_b])

        with patch(f"{self._MOD}.prompt_select", return_value="default/qwen2.5:1.5b") as mock_prompt_select:
            result = _select_default_model(client, "default")

        assert result == "default/qwen2.5:1.5b"
        assert mock_prompt_select.call_args.kwargs["choices"] == [
            (
                "default/meta-llama-3-1-8b-instruct",
                "meta-llama-3-1-8b-instruct (nvidia-build)",
            ),
            (
                "default/qwen2.5:1.5b",
                "qwen2.5:1.5b (my-ollama-custom)",
            ),
        ]


# ---------------------------------------------------------------------------
# API key validation
# ---------------------------------------------------------------------------


class TestValidateApiKey:
    """Tests for _validate_api_key — probes provider to detect bad credentials."""

    _MOD = "nemo_platform_ext.cli.commands.setup"

    @pytest.mark.parametrize(
        "provider_name,status_code,expected_passed",
        [
            ("nvidia-build", 400, True),
            ("nvidia-build", 401, False),
            ("nvidia-build", 403, False),
            ("nvidia-build", 200, True),
            ("openai", 200, True),
            ("openai", 401, False),
        ],
    )
    def test_http_responses(self, provider_name, status_code, expected_passed):
        host_url = _KNOWN_PROVIDERS_BY_NAME[provider_name].host_url
        mock_resp = MagicMock(status_code=status_code)
        with patch(f"{self._MOD}.httpx.request", return_value=mock_resp):
            result = _validate_api_key(provider_name, host_url, "test-key")
        assert result.passed is expected_passed

    @pytest.mark.parametrize("status_code", [404, 429, 500, 502])
    def test_non_2xx_non_rejection_returns_warning(self, status_code):
        mock_resp = MagicMock(status_code=status_code)
        with patch(f"{self._MOD}.httpx.request", return_value=mock_resp):
            result = _validate_api_key("nvidia-build", "https://integrate.api.nvidia.com", "test-key")
        assert result.passed is True
        assert f"HTTP {status_code}" in result.message

    @pytest.mark.parametrize(
        "provider_name,api_key,side_effect,expected_passed",
        [
            ("nvidia-build", "k", httpx.TimeoutException("timeout"), True),
            ("nvidia-build", "k", httpx.ConnectError("refused"), True),
            ("custom-thing", "k", None, True),
            ("nvidia-build", None, None, True),
        ],
        ids=["timeout", "connect-error", "unknown-provider", "no-api-key"],
    )
    def test_skip_and_error_paths(self, provider_name, api_key, side_effect, expected_passed):
        with patch(f"{self._MOD}.httpx.request", side_effect=side_effect) as mock_req:
            result = _validate_api_key(provider_name, "https://example.com", api_key)
        assert result.passed is expected_passed
        if api_key is None or provider_name not in _PROBE_CONFIGS:
            mock_req.assert_not_called()

    def test_custom_auth_header_format(self):
        """Anthropic-style 'X-Api-Key: {{ auth_secret }}' header should be constructed."""
        mock_resp = MagicMock(status_code=400)
        with patch(f"{self._MOD}.httpx.request", return_value=mock_resp) as mock_req:
            _validate_api_key(
                "nvidia-build",
                "https://integrate.api.nvidia.com",
                "my-secret-key",
                auth_header_format="X-Api-Key: {{ auth_secret }}",
            )
        _, kwargs = mock_req.call_args
        assert kwargs["headers"]["X-Api-Key"] == "my-secret-key"
        assert "Authorization" not in kwargs["headers"]

    def test_extra_headers_included(self):
        """default_extra_headers should be merged into the probe request."""
        mock_resp = MagicMock(status_code=400)
        extra = {"anthropic-version": "2023-06-01"}
        with patch(f"{self._MOD}.httpx.request", return_value=mock_resp) as mock_req:
            _validate_api_key(
                "nvidia-build",
                "https://integrate.api.nvidia.com",
                "test-key",
                default_extra_headers=extra,
            )
        _, kwargs = mock_req.call_args
        assert kwargs["headers"]["anthropic-version"] == "2023-06-01"


class TestValidateApiKeyIntegration:
    """Tests that _validate_api_key gates model discovery in interactive and auto flows."""

    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_interactive_invalid_key_blocks_discovery(self):
        """When key validation fails, _wait_for_models must not be called."""
        with (
            patch(
                f"{self._MOD}._interactive_collect_provider",
                return_value=("nvidia-build", "https://integrate.api.nvidia.com", "bad-key", None, None),
            ),
            patch(f"{self._MOD}._register_provider_interactive"),
            patch(
                f"{self._MOD}._validate_api_key",
                return_value=KeyValidationResult(passed=False, message="API key rejected"),
            ),
            patch(f"{self._MOD}._wait_for_models") as mock_wait,
            patch(f"{self._MOD}.console"),
            pytest.raises(ClickExit) as exc_info,
        ):
            cli_ctx = MagicMock()
            _run_interactive_mode(
                cli_ctx,
                _make_mock_client(),
                "default",
                "http://localhost:8080",
                None,
                None,
            )
        assert exc_info.value.exit_code == 1
        mock_wait.assert_not_called()

    def test_auto_invalid_key_raises_exit(self):
        """When key validation fails in auto mode, _auto_setup should raise typer.Exit(1)."""
        client = _make_mock_client()
        with (
            patch.dict("os.environ", {"NVIDIA_API_KEY": "bad-key"}, clear=True),
            patch(
                f"{self._MOD}._validate_api_key",
                return_value=KeyValidationResult(passed=False, message="API key rejected"),
            ),
            patch(f"{self._MOD}.console"),
            pytest.raises(ClickExit) as exc_info,
        ):
            _auto_setup(client, "default")
        assert exc_info.value.exit_code == 1


# ---------------------------------------------------------------------------
# Polling constants — tighter intervals for localhost responsiveness
# ---------------------------------------------------------------------------


@pytest.fixture
def spinner_console():
    """Patch console with a mock status spinner context manager."""
    mock_status = MagicMock()
    with patch("nemo_platform_ext.cli.commands.setup.console") as mock_console:
        mock_console.status.return_value.__enter__ = MagicMock(return_value=mock_status)
        mock_console.status.return_value.__exit__ = MagicMock(return_value=False)
        yield mock_console, mock_status


class TestPollingConstants:
    @pytest.mark.parametrize(
        "constant",
        [
            _SERVICE_STARTUP_POLL_INTERVAL,
            _MODEL_DISCOVERY_POLL_INTERVAL,
            _AGENT_DEPLOY_POLL_INTERVAL,
            _AGENT_API_READINESS_POLL_INTERVAL,
        ],
    )
    def test_poll_intervals_are_at_most_one_second(self, constant):
        assert constant <= 1


# ---------------------------------------------------------------------------
# Progress spinner tests — _wait_for_platform
# ---------------------------------------------------------------------------


class TestWaitForPlatformSpinner:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_shows_spinner_while_waiting(self, spinner_console):
        """console.status() should be used as a context manager during polling."""
        mock_console, _ = spinner_console
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0.5, 1, 1]),
            patch(f"{self._MOD}._check_platform_reachable", side_effect=[False, True]),
        ):
            result = _wait_for_platform("http://localhost:8080")

        assert result is True
        mock_console.status.assert_called_once()

    def test_spinner_updates_with_elapsed_time(self, spinner_console):
        """status.update() should include elapsed seconds."""
        _, mock_status = spinner_console
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 2, 4, 4, 6, 6]),
            patch(f"{self._MOD}._check_platform_reachable", side_effect=[False, False, True]),
        ):
            _wait_for_platform("http://localhost:8080")

        update_texts = [c.args[0] for c in mock_status.update.call_args_list]
        assert any("2s" in t for t in update_texts), f"Expected elapsed time in updates: {update_texts}"

    def test_spinner_stops_on_timeout(self, spinner_console):
        """Spinner exits cleanly and function returns False on timeout."""
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 200, 200]),
            patch(f"{self._MOD}._check_platform_reachable", return_value=False),
        ):
            result = _wait_for_platform("http://localhost:8080", timeout=120)

        assert result is False

    def test_uses_reduced_http_timeout(self, spinner_console):
        """Health check should use a short HTTP timeout (<=1.5s) for fast cycles."""
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0.5, 1]),
            patch(f"{self._MOD}._check_platform_reachable", side_effect=[True]) as mock_reachable,
        ):
            _wait_for_platform("http://localhost:8080")

        _, kwargs = mock_reachable.call_args
        assert kwargs.get("timeout", 999) <= 1.5

    def test_spinner_shows_last_loaded_service(self, spinner_console, tmp_path):
        """When a log_path is provided, the spinner should include the service name."""
        _, mock_status = spinner_console
        log = tmp_path / "services.log"
        log.write_text("[STARTUP] service:auth: 500ms\n[STARTUP] service:guardrails: 40000ms\n")

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 5, 10, 10]),
            patch(f"{self._MOD}._check_platform_reachable", side_effect=[False, True]),
        ):
            result = _wait_for_platform("http://localhost:8080", log_path=log)

        assert result is True
        update_texts = [c.args[0] for c in mock_status.update.call_args_list]
        assert any("guardrails" in t for t in update_texts), f"Expected service name in updates: {update_texts}"

    def test_spinner_works_without_log_path(self, spinner_console):
        """Spinner should work normally when no log_path is provided."""
        _, mock_status = spinner_console
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 2, 4, 4]),
            patch(f"{self._MOD}._check_platform_reachable", side_effect=[False, True]),
        ):
            result = _wait_for_platform("http://localhost:8080", log_path=None)

        assert result is True
        update_texts = [c.args[0] for c in mock_status.update.call_args_list]
        assert all("loaded" not in t for t in update_texts)


# ---------------------------------------------------------------------------
# _last_startup_service tests
# ---------------------------------------------------------------------------


class TestLastStartupService:
    def test_parses_last_service(self, tmp_path):
        log = tmp_path / "services.log"
        log.write_text(
            "[STARTUP] service:auth: 500ms\n[STARTUP] service:files: 3000ms\n[STARTUP] service:guardrails: 40000ms\n"
        )
        assert _last_startup_service(log) == "guardrails"

    def test_returns_empty_for_missing_file(self, tmp_path):
        assert _last_startup_service(tmp_path / "nonexistent.log") == ""

    def test_returns_empty_for_none(self):
        assert _last_startup_service(None) == ""

    def test_returns_empty_for_no_startup_lines(self, tmp_path):
        log = tmp_path / "services.log"
        log.write_text("some other log content\n")
        assert _last_startup_service(log) == ""


# ---------------------------------------------------------------------------
# Default timeout constant
# ---------------------------------------------------------------------------


class TestDefaultTimeout:
    def test_default_startup_timeout_is_240(self):
        assert _SERVICE_STARTUP_TIMEOUT_SECONDS == 240


# ---------------------------------------------------------------------------
# Progress spinner tests — _wait_for_models
# ---------------------------------------------------------------------------


class TestWaitForModelsSpinner:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_shows_spinner_during_model_discovery(self, spinner_console):
        """console.status() should be active during model discovery polling."""
        mock_console, _ = spinner_console
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 100]),
        ):
            _wait_for_models(client, "nvidia-build", "default", round_seconds=5, max_rounds=1)

        mock_console.status.assert_called()

    def test_spinner_updates_with_elapsed_time(self, spinner_console):
        """status.update() should include elapsed seconds during model polling."""
        _, mock_status = spinner_console
        client = MagicMock()
        model = MagicMock()
        model.model_entity_id = "default/nvidia-llama"
        client.inference.providers.retrieve.side_effect = [
            MagicMock(served_models=[]),
            MagicMock(served_models=[model]),
        ]

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 1, 2, 3]),
        ):
            result = _wait_for_models(client, "nvidia-build", "default", round_seconds=30, max_rounds=1)

        assert result == ["default/nvidia-llama"]
        update_texts = [c.args[0] for c in mock_status.update.call_args_list]
        assert any("s)" in t for t in update_texts), f"Expected elapsed time in updates: {update_texts}"

    def test_continues_polling_when_served_models_lack_entity_ids(self, spinner_console):
        """Polling should continue when served_models exist but have no entity IDs."""
        client = MagicMock()
        model_without_id = MagicMock(spec=[])
        model_with_id = MagicMock()
        model_with_id.model_entity_id = "default/nvidia-llama"
        client.inference.providers.retrieve.side_effect = [
            MagicMock(served_models=[model_without_id]),
            MagicMock(served_models=[model_with_id]),
        ]

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 1, 2, 3]),
        ):
            result = _wait_for_models(client, "nvidia-build", "default", round_seconds=30, max_rounds=1)

        assert result == ["default/nvidia-llama"]


# ---------------------------------------------------------------------------
# Early exit tests — _wait_for_models
# ---------------------------------------------------------------------------


class TestWaitForModelsEarlyExit:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_exits_early_on_non_compliant_provider(self, spinner_console):
        """Returns [] immediately when provider status_message indicates non-compliant."""
        mock_console, _ = spinner_console
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        provider.status = "READY"
        provider.status_message = "Non-OpenAI compliant endpoint, model entity routing disabled"
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 0]),
        ):
            result = _wait_for_models(
                client,
                "bad-provider",
                "default",
                host_url="https://inference.nvidia.com",
                round_seconds=30,
                max_rounds=2,
            )

        assert result == []
        assert client.inference.providers.retrieve.call_count == 1
        mock_console.print.assert_any_call(
            "\n  [yellow]![/yellow] Provider 'bad-provider' (https://inference.nvidia.com) "
            "returned a non-OpenAI compliant response from GET /v1/models."
        )

    def test_exits_early_on_error_status(self, spinner_console):
        """Returns [] immediately when provider status is ERROR."""
        _mock_console, _ = spinner_console
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        provider.status = "ERROR"
        provider.status_message = "Provider discovery failed: Gateway error (HTTP 502)"
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 0]),
        ):
            result = _wait_for_models(
                client,
                "broken-provider",
                "default",
                host_url="https://example.com",
                round_seconds=30,
                max_rounds=2,
            )

        assert result == []
        assert client.inference.providers.retrieve.call_count == 1

    def test_exits_early_on_lost_status(self, spinner_console):
        """Returns [] immediately when provider status is LOST."""
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        provider.status = "LOST"
        provider.status_message = "Provider discovery permanently failed."
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 0]),
        ):
            result = _wait_for_models(client, "lost-provider", "default", round_seconds=30, max_rounds=2)

        assert result == []

    def test_no_false_positive_on_created_status(self, spinner_console):
        """CREATED status with no status_message should NOT trigger early exit."""
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        provider.status = "CREATED"
        provider.status_message = None
        client.inference.providers.retrieve.return_value = provider

        # monotonic calls: start, deadline, while-check, elapsed, while-check, elapsed, while-check(exit)
        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 1, 2, 2, 100]),
        ):
            result = _wait_for_models(client, "new-provider", "default", round_seconds=5, max_rounds=1)

        assert result == []
        assert client.inference.providers.retrieve.call_count > 1

    def test_models_found_before_non_compliant(self, spinner_console):
        """If models appear on the same poll, served_models are checked first."""
        client = MagicMock()
        model = MagicMock()
        model.model_entity_id = "default/my-model"
        provider = MagicMock()
        provider.served_models = [model]
        provider.status = "READY"
        provider.status_message = None
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 0]),
        ):
            result = _wait_for_models(client, "good-provider", "default", round_seconds=30, max_rounds=1)

        assert result == ["default/my-model"]

    def test_host_url_omitted_in_warning(self, spinner_console):
        """When host_url is empty the warning should not include a parenthetical."""
        mock_console, _ = spinner_console
        client = MagicMock()
        provider = MagicMock()
        provider.served_models = []
        provider.status = "READY"
        provider.status_message = "Non-OpenAI compliant endpoint, model entity routing disabled"
        client.inference.providers.retrieve.return_value = provider

        with (
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 0, 0]),
        ):
            _wait_for_models(client, "bad-provider", "default", round_seconds=30, max_rounds=1)

        printed = [str(c) for c in mock_console.print.call_args_list]
        assert not any("()" in p for p in printed)


# ---------------------------------------------------------------------------
# Progress spinner tests — _deploy_demo_agent
# ---------------------------------------------------------------------------


class TestDeployDemoAgentSpinner:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_agent_config_path_finds_package_local_yaml(self, monkeypatch, tmp_path):
        """Packaged wheels bundle calculator-agent.yml inside the calculator_agent package."""
        package_dir = tmp_path / "calculator_agent"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        config = package_dir / "calculator-agent.yml"
        config.write_text("llms: {}\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.delitem(sys.modules, "calculator_agent", raising=False)

        assert _agent_config_path() == config

    def test_agent_config_path_finds_namespace_package_yaml(self, monkeypatch, tmp_path):
        """calculator_agent is an implicit namespace package, so __file__ may be None."""
        package_dir = tmp_path / "calculator_agent"
        package_dir.mkdir()
        config = package_dir / "calculator-agent.yml"
        config.write_text("llms: {}\n", encoding="utf-8")
        monkeypatch.syspath_prepend(str(tmp_path))
        monkeypatch.delitem(sys.modules, "calculator_agent", raising=False)

        assert _agent_config_path() == config

    def _mock_deploy_responses(self, *, status_sequence):
        """Build httpx response mocks for create + deployment status polling.

        The deploy POST returns the full entity including its unique ``name``
        so the polling loop can GET that specific deployment by name.
        """
        create_resp = MagicMock()
        create_resp.status_code = 200
        create_resp.raise_for_status = MagicMock()

        deploy_resp = MagicMock()
        deploy_resp.status_code = 200
        deploy_resp.raise_for_status = MagicMock()
        deploy_resp.json.return_value = {
            "name": "calculator-agent-abc12345",
            "agent": "calculator-agent",
            "status": "pending",
        }

        status_resps = []
        for s in status_sequence:
            r = MagicMock()
            r.status_code = 200
            r.json.return_value = {"name": "calculator-agent-abc12345", "agent": "calculator-agent", "status": s}
            status_resps.append(r)

        return [create_resp, deploy_resp] + status_resps

    def test_shows_spinner_during_deployment_wait(self, tmp_path, spinner_console):
        """console.status() should be active while polling deployment status."""
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")

        responses = self._mock_deploy_responses(status_sequence=["pending", "running"])
        mock_console, _ = spinner_console

        with (
            patch(f"{self._MOD}.httpx.get", side_effect=responses[2:]),
            patch(f"{self._MOD}.httpx.post", side_effect=responses[:2]),
            patch(f"{self._MOD}._agent_exists", return_value=False),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 3]),
        ):
            result = _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")

        assert result is True
        mock_console.status.assert_called()

    def test_spinner_updates_with_elapsed_time(self, tmp_path, spinner_console):
        """status.update() should include elapsed seconds during deploy polling."""
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")

        responses = self._mock_deploy_responses(status_sequence=["pending", "pending", "running"])
        _, mock_status = spinner_console

        with (
            patch(f"{self._MOD}.httpx.get", side_effect=responses[2:]),
            patch(f"{self._MOD}.httpx.post", side_effect=responses[:2]),
            patch(f"{self._MOD}._agent_exists", return_value=False),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 3, 4, 5]),
        ):
            _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")

        update_texts = [c.args[0] for c in mock_status.update.call_args_list]
        assert any("s)" in t for t in update_texts), f"Expected elapsed time in updates: {update_texts}"

    def test_uses_reduced_http_timeout(self, tmp_path, spinner_console):
        """Deployment status GET should use a short HTTP timeout (<=3s)."""
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")

        responses = self._mock_deploy_responses(status_sequence=["running"])

        with (
            patch(f"{self._MOD}.httpx.get", side_effect=responses[2:]) as mock_get,
            patch(f"{self._MOD}.httpx.post", side_effect=responses[:2]),
            patch(f"{self._MOD}._agent_exists", return_value=False),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2]),
        ):
            _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")

        get_calls = mock_get.call_args_list
        for c in get_calls:
            assert c.kwargs.get("timeout", 999) <= 3.0

    def test_polls_specific_deployment_by_name(self, tmp_path, spinner_console):
        """The poll must GET the specific deployment, not list all deployments."""
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms: {}\n")

        responses = self._mock_deploy_responses(status_sequence=["running"])

        with (
            patch(f"{self._MOD}.httpx.get", side_effect=responses[2:]) as mock_get,
            patch(f"{self._MOD}.httpx.post", side_effect=responses[:2]),
            patch(f"{self._MOD}._agent_exists", return_value=False),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2]),
        ):
            result = _deploy_demo_agent("http://localhost:8080", "default", config, default_model="m")

        assert result is True
        url = mock_get.call_args_list[0].args[0]
        assert "/deployments/calculator-agent-abc12345" in url

    def test_expands_default_model_placeholder_on_create(self, tmp_path, spinner_console):
        """The built-in YAML uses ``${NEMO_DEFAULT_MODEL}``; resolve before POST
        because the agents service has no user context to resolve it itself.
        Regression for AIRCORE-601.
        """
        config = tmp_path / "calculator-agent.yml"
        config.write_text("llms:\n  agent:\n    _type: openai\n    model_name: ${NEMO_DEFAULT_MODEL}\n")

        responses = self._mock_deploy_responses(status_sequence=["running"])

        with (
            patch(f"{self._MOD}.httpx.get", side_effect=responses[2:]),
            patch(f"{self._MOD}.httpx.post", side_effect=responses[:2]) as mock_post,
            patch(f"{self._MOD}._agent_exists", return_value=False),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2]),
        ):
            _deploy_demo_agent(
                "http://localhost:8080",
                "default",
                config,
                default_model="nvidia-nemotron-3-super-v3",
            )

        create_call = mock_post.call_args_list[0]
        sent_config = create_call.kwargs["json"]["config"]
        assert sent_config["llms"]["agent"]["model_name"] == "nvidia-nemotron-3-super-v3"


# ---------------------------------------------------------------------------
# `_maybe_deploy_agent` guards
# ---------------------------------------------------------------------------


class TestMaybeDeployAgentGuards:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_skips_deploy_when_default_model_missing(self):
        """No default model selected → skip deploy so the agent service never
        stores an unresolved ``${NEMO_DEFAULT_MODEL}``. Regression for AIRCORE-601.
        """
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._deploy_demo_agent") as mock_deploy,
        ):
            result = _maybe_deploy_agent(
                "http://localhost:8080",
                "default",
                auto=True,
                deploy_agent=True,
                default_model=None,
            )

        mock_deploy.assert_not_called()
        assert result is False

    def test_returns_false_when_plugin_unavailable(self):
        with patch(f"{self._MOD}._agents_plugin_available", return_value=False):
            result = _maybe_deploy_agent(
                "http://localhost:8080", "default", auto=True, deploy_agent=True, default_model="m"
            )
        assert result is False

    def test_returns_false_in_auto_mode_without_explicit_flag(self):
        with patch(f"{self._MOD}._agents_plugin_available", return_value=True):
            result = _maybe_deploy_agent(
                "http://localhost:8080", "default", auto=True, deploy_agent=None, default_model="m"
            )
        assert result is False

    def test_returns_false_when_config_path_missing(self):
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._agent_config_path", return_value=None),
        ):
            result = _maybe_deploy_agent(
                "http://localhost:8080", "default", auto=True, deploy_agent=True, default_model="m"
            )
        assert result is False

    def test_returns_true_on_successful_deploy(self, spinner_console):
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._agent_config_path", return_value=MagicMock()),
            patch(f"{self._MOD}._agents_api_ready", return_value=True),
            patch(f"{self._MOD}._deploy_demo_agent", return_value=True),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1]),
        ):
            result = _maybe_deploy_agent(
                "http://localhost:8080", "default", auto=False, deploy_agent=True, default_model="m"
            )
        assert result is True

    def test_returns_false_when_deploy_raises(self, spinner_console):
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._agent_config_path", return_value=MagicMock()),
            patch(f"{self._MOD}._agents_api_ready", return_value=True),
            patch(f"{self._MOD}._deploy_demo_agent", side_effect=RuntimeError("boom")),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1]),
        ):
            result = _maybe_deploy_agent(
                "http://localhost:8080", "default", auto=False, deploy_agent=True, default_model="m"
            )
        assert result is False


# ---------------------------------------------------------------------------
# Progress spinner tests — agents API readiness in _maybe_deploy_agent
# ---------------------------------------------------------------------------


class TestAgentsApiReadinessSpinner:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_shows_spinner_while_waiting_for_agents_api(self, spinner_console):
        """console.status() should be active while waiting for agents API readiness."""
        mock_console, _ = spinner_console
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._agent_config_path", return_value=MagicMock()),
            patch(f"{self._MOD}._agents_api_ready", side_effect=[False, True]),
            patch(f"{self._MOD}._deploy_demo_agent", return_value=True),
            patch(f"{self._MOD}._pause"),
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 3]),
        ):
            _maybe_deploy_agent("http://localhost:8080", "default", auto=False, deploy_agent=True, default_model="m")

        mock_console.status.assert_called()

    def test_uses_poll_interval_constant(self, spinner_console):
        """Should use _AGENT_API_READINESS_POLL_INTERVAL, not a hardcoded value."""
        with (
            patch(f"{self._MOD}._agents_plugin_available", return_value=True),
            patch(f"{self._MOD}._agent_config_path", return_value=MagicMock()),
            patch(f"{self._MOD}._agents_api_ready", side_effect=[False, True]),
            patch(f"{self._MOD}._deploy_demo_agent", return_value=True),
            patch(f"{self._MOD}._pause") as mock_pause,
            patch(f"{self._MOD}.time.monotonic", side_effect=[0, 0, 1, 2, 3]),
        ):
            _maybe_deploy_agent("http://localhost:8080", "default", auto=False, deploy_agent=True, default_model="m")

        pause_values = [c.args[0] for c in mock_pause.call_args_list]
        assert all(v == _AGENT_API_READINESS_POLL_INTERVAL for v in pause_values)


# ---------------------------------------------------------------------------
# Custom provider prompt
# ---------------------------------------------------------------------------


class TestPromptCustomProvider:
    _MOD = "nemo_platform_ext.cli.commands.setup"

    def test_prompt_passes_validator(self):
        """The provider name prompt should include a validator."""
        with (
            patch(f"{self._MOD}.prompt_text", return_value="my-provider") as mock_prompt,
            patch(f"{self._MOD}.prompt_password", return_value=""),
        ):
            _prompt_custom_provider()
        name_call = mock_prompt.call_args_list[0]
        assert name_call.kwargs.get("validator") is not None

    def test_prompt_passes_hint(self):
        """The provider name prompt should include a naming hint."""
        with (
            patch(f"{self._MOD}.prompt_text", return_value="my-provider") as mock_prompt,
            patch(f"{self._MOD}.prompt_password", return_value=""),
        ):
            _prompt_custom_provider()
        name_call = mock_prompt.call_args_list[0]
        hint = name_call.kwargs.get("hint")
        assert hint is not None
        assert "lowercase" in hint.lower()


# ---------------------------------------------------------------------------
# Non-TTY early exit guard
# ---------------------------------------------------------------------------


class TestNonTtyEarlyExit:
    """setup_command must exit(1) when stdin is not a TTY and --auto is not passed."""

    def _invoke(self, *, auto: bool = False):
        """Invoke setup_command with a minimal mock context."""
        ctx = MagicMock(spec=typer.Context)
        cli_context = MagicMock()
        cli_context.get_base_url.return_value = "http://localhost:8080"
        ctx.obj = cli_context
        setup_command(ctx, auto=auto)

    def test_exits_when_non_tty_without_auto(self):
        with (
            patch(f"{SETUP_MOD}.is_interactive", return_value=False),
            pytest.raises(typer.Exit) as exc_info,
        ):
            self._invoke(auto=False)
        assert exc_info.value.exit_code == 1

    def test_proceeds_when_non_tty_with_auto(self):
        with (
            patch(f"{SETUP_MOD}.is_interactive", return_value=False),
            patch(f"{SETUP_MOD}._maybe_start_services"),
            patch(f"{SETUP_MOD}._check_platform_reachable_with_retries", return_value=True),
            patch(f"{SETUP_MOD}._bootstrap_config_if_missing"),
            patch(f"{SETUP_MOD}._run_auto_mode"),
        ):
            self._invoke(auto=True)

    def test_proceeds_when_tty_without_auto(self):
        with (
            patch(f"{SETUP_MOD}.is_interactive", return_value=True),
            patch(f"{SETUP_MOD}._maybe_start_services"),
            patch(f"{SETUP_MOD}._check_platform_reachable_with_retries", return_value=True),
            patch(f"{SETUP_MOD}._bootstrap_config_if_missing"),
            patch(f"{SETUP_MOD}._run_interactive_mode"),
        ):
            self._invoke(auto=False)


# ---------------------------------------------------------------------------
# Controller health check
# ---------------------------------------------------------------------------


def _status_response(*, healthy: bool = True, controller_status: dict | None = None):
    """Build a mock httpx.Response for GET /status."""
    body = {
        "status": "healthy" if healthy else "degraded",
        "services": {"ready": ["auth", "models"], "not_ready": []},
        "controllers": {
            "healthy": healthy,
            "status": controller_status if controller_status is not None else {},
        },
    }
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = body
    return resp


class TestCheckControllerHealth:
    def test_healthy_controllers(self):
        resp = _status_response(healthy=True, controller_status={"models_controller": True})
        with patch(f"{SETUP_MOD}.httpx.get", return_value=resp):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is True
        assert msg == ""

    def test_unhealthy_controller(self):
        resp = _status_response(healthy=False, controller_status={"models_controller": False})
        with patch(f"{SETUP_MOD}.httpx.get", return_value=resp):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "models_controller" in msg

    def test_empty_controllers_retries_then_succeeds(self):
        empty_resp = _status_response(healthy=True, controller_status={})
        populated_resp = _status_response(healthy=True, controller_status={"models_controller": True})
        with (
            patch(f"{SETUP_MOD}.httpx.get", side_effect=[empty_resp, populated_resp]),
            patch(f"{SETUP_MOD}._pause") as mock_pause,
        ):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is True
        assert msg == ""
        mock_pause.assert_called_once_with(_CONTROLLER_HEALTH_RETRY_DELAY)

    def test_empty_controllers_retries_then_still_empty(self):
        empty_resp = _status_response(healthy=True, controller_status={})
        with (
            patch(f"{SETUP_MOD}.httpx.get", return_value=empty_resp),
            patch(f"{SETUP_MOD}._pause"),
        ):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "no controllers" in msg.lower()

    def test_endpoint_unreachable(self):
        with patch(f"{SETUP_MOD}.httpx.get", side_effect=httpx.ConnectError("refused")):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "could not reach" in msg.lower()

    def test_non_200_response(self):
        resp = MagicMock()
        resp.status_code = 500
        with patch(f"{SETUP_MOD}.httpx.get", return_value=resp):
            ok, _ = _check_controller_health("http://localhost:8080")
        assert ok is False

    def test_invalid_json_response(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.side_effect = ValueError("not json")
        with patch(f"{SETUP_MOD}.httpx.get", return_value=resp):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "invalid json" in msg.lower()

    def test_malformed_controllers_payload(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "healthy", "controllers": None}
        with patch(f"{SETUP_MOD}.httpx.get", return_value=resp):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "invalid" in msg.lower()

    def test_malformed_status_list_treated_as_empty(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"status": "healthy", "controllers": {"healthy": True, "status": [1, 2]}}
        with (
            patch(f"{SETUP_MOD}.httpx.get", return_value=resp),
            patch(f"{SETUP_MOD}._pause"),
        ):
            ok, msg = _check_controller_health("http://localhost:8080")
        assert ok is False
        assert "no controllers" in msg.lower()


class TestVerifyPlatformHealth:
    def test_healthy_returns_true(self):
        with patch(f"{SETUP_MOD}._check_controller_health", return_value=(True, "")):
            result = _verify_platform_health("http://localhost:8080")
        assert result is True

    def test_unhealthy_prints_red_error(self):
        with (
            patch(f"{SETUP_MOD}._check_controller_health", return_value=(False, "models_controller unhealthy")),
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            result = _verify_platform_health("http://localhost:8080")
        assert result is False
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "red" in printed.lower()
        assert "nemo services run" in printed

    def test_empty_after_retry_prints_yellow_warning(self):
        with (
            patch(f"{SETUP_MOD}._check_controller_health", return_value=(False, "no controllers reported status")),
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            result = _verify_platform_health("http://localhost:8080")
        assert result is False
        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "yellow" in printed.lower() or "nemo services status" in printed


class TestRenderOnboardingCard:
    def test_optimize_card_includes_note(self):
        with patch(f"{SETUP_MOD}.console") as mock_console:
            _render_onboarding_card("optimize")

        panel = mock_console.print.call_args_list[0].args[0]
        assert "agent's project directory" in panel.renderable

    def test_explore_card_contains_skill_prompt_and_docs(self):
        with patch(f"{SETUP_MOD}.console") as mock_console:
            _render_onboarding_card("explore")

        panel = mock_console.print.call_args_list[0].args[0]
        content = panel.renderable
        assert "What can I do with NeMo Platform?" in content
        assert "nvidia-nemo.github.io/nemo-platform" in content

    def test_unknown_value_is_silently_skipped(self):
        with patch(f"{SETUP_MOD}.console") as mock_console:
            _render_onboarding_card("nonexistent")

        mock_console.print.assert_not_called()

    def test_all_paths_render_without_error(self):
        for path in ONBOARDING_PATHS:
            with patch(f"{SETUP_MOD}.console") as mock_console:
                _render_onboarding_card(path.value)

            panel = mock_console.print.call_args_list[0].args[0]
            assert hasattr(panel, "renderable")


class TestPrintOnboarding:
    def test_shows_setup_complete_and_choice(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="optimize") as mock_choice,
            patch(f"{SETUP_MOD}._render_onboarding_card") as mock_card,
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", "default/some-model")

        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "Setup complete" in printed
        assert "nvidia-build" in printed
        mock_choice.assert_called_once()
        mock_card.assert_called_once_with("optimize")

    def test_explore_path_renders_card(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="explore"),
            patch(f"{SETUP_MOD}._render_onboarding_card") as mock_card,
            patch(f"{SETUP_MOD}.console"),
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", None)

        mock_card.assert_called_once_with("explore")

    def test_unhealthy_platform_exits(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=False),
            pytest.raises((typer.Exit, SystemExit)),
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", None)

    def test_default_model_shown_when_present(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="explore"),
            patch(f"{SETUP_MOD}._render_onboarding_card"),
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", "default/llama-3-3")

        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "llama-3-3" in printed

    def test_demo_agent_shown_when_deployed(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="explore"),
            patch(f"{SETUP_MOD}._render_onboarding_card"),
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", "m", demo_deployed=True)

        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "calculator-agent" in printed

    def test_demo_agent_hidden_when_not_deployed(self):
        with (
            patch(f"{SETUP_MOD}._verify_platform_health", return_value=True),
            patch(f"{SETUP_MOD}.prompt_choice", return_value="explore"),
            patch(f"{SETUP_MOD}._render_onboarding_card"),
            patch(f"{SETUP_MOD}.console") as mock_console,
        ):
            _print_onboarding("http://localhost:8080", "nvidia-build", "m", demo_deployed=False)

        printed = " ".join(str(c) for c in mock_console.print.call_args_list)
        assert "calculator-agent" not in printed
