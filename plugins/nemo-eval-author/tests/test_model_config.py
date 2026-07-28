# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Credential and model-client resolution for Eval Author."""

import os
import subprocess
import sys
from collections.abc import Iterator

import pytest
from nemo_eval_author_plugin import model_config


@pytest.fixture(autouse=True)
def _clear_model_cache() -> Iterator[None]:
    """Drop every cached client so each test resolves credentials from scratch."""

    def clear() -> None:
        model_config.get_smart_model.cache_clear()
        model_config.get_fast_model.cache_clear()
        model_config._completion_client.cache_clear()

    clear()
    yield
    clear()


def test_api_base_prefers_eval_author_over_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")

    assert model_config._api_base() == "https://eval-author.example/v1"


def test_api_base_falls_back_to_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AUTHOR_API_BASE", raising=False)
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "exp-key")

    assert model_config._api_base() == "https://experimentalist.example/v1"


def test_api_base_requires_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AUTHOR_API_BASE", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_BASE", raising=False)

    with pytest.raises(ValueError, match="AUTHOR_API_BASE"):
        model_config._api_base()


def test_whitespace_only_values_count_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "   ")
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "  https://experimentalist.example/v1  ")

    assert model_config._api_base() == "https://experimentalist.example/v1"


def test_api_key_accepts_inference_key_on_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://inference-api.nvidia.com/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.setenv("INFERENCE_API_KEY", "sk-gateway")

    assert model_config._api_key() == "sk-gateway"


def test_api_key_refuses_to_forward_inference_key_over_plain_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "http://inference-api.nvidia.com/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.setenv("INFERENCE_API_KEY", "sk-gateway")

    with pytest.raises(ValueError, match="AUTHOR_API_KEY"):
        model_config._api_key()


def test_api_key_refuses_to_forward_inference_key_to_a_lookalike_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://inference-api.nvidia.com.attacker.example/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.setenv("INFERENCE_API_KEY", "sk-gateway")

    with pytest.raises(ValueError, match="AUTHOR_API_KEY"):
        model_config._api_key()


def test_api_key_requires_credentials_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://custom.example/v1")
    monkeypatch.delenv("AUTHOR_API_KEY", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    monkeypatch.delenv("INFERENCE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="AUTHOR_API_KEY"):
        model_config._api_key()


@pytest.mark.parametrize("tier", ["SMART", "FAST"])
def test_model_name_prefers_author_then_experimentalist_then_default(
    monkeypatch: pytest.MonkeyPatch,
    tier: str,
) -> None:
    getter = {"SMART": model_config.get_smart_model, "FAST": model_config.get_fast_model}[tier]
    default = {"SMART": model_config._SMART_MODEL_DEFAULT, "FAST": model_config._FAST_MODEL_DEFAULT}[tier]
    author_var = f"AUTHOR_{tier}_MODEL_NAME"
    experimentalist_var = f"EXPERIMENTALIST_{tier}_MODEL_NAME"

    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")

    monkeypatch.setenv(author_var, "vendor/from-author")
    monkeypatch.setenv(experimentalist_var, "vendor/from-experimentalist")
    assert getter().model == "vendor/from-author"

    getter.cache_clear()
    monkeypatch.delenv(author_var)
    assert getter().model == "vendor/from-experimentalist"

    getter.cache_clear()
    monkeypatch.delenv(experimentalist_var)
    assert getter().model == default


def test_tiers_pointing_at_one_model_share_a_client(monkeypatch: pytest.MonkeyPatch) -> None:
    # The @functools.cache on each getter only promises one client per tier. Caching the
    # factory on the resolved triple is what collapses tiers that resolve identically.
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")
    monkeypatch.setenv("AUTHOR_SMART_MODEL_NAME", "vendor/one-model")
    monkeypatch.setenv("AUTHOR_FAST_MODEL_NAME", "vendor/one-model")

    assert model_config.get_smart_model() is model_config.get_fast_model()


def test_differing_tiers_get_separate_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")
    monkeypatch.setenv("AUTHOR_SMART_MODEL_NAME", "vendor/smart")
    monkeypatch.setenv("AUTHOR_FAST_MODEL_NAME", "vendor/fast")

    assert model_config.get_smart_model() is not model_config.get_fast_model()


def test_bridge_author_env_fills_unset_experimentalist_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("AUTHOR_API_KEY", "eval-key")
    monkeypatch.delenv("EXPERIMENTALIST_API_BASE", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)

    applied = model_config.bridge_author_env_to_experimentalist()

    assert applied == ["EXPERIMENTALIST_API_BASE", "EXPERIMENTALIST_API_KEY"]
    assert os.environ["EXPERIMENTALIST_API_BASE"] == "https://eval-author.example/v1"
    assert os.environ["EXPERIMENTALIST_API_KEY"] == "eval-key"


def test_bridge_author_env_covers_every_declared_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for src, dst in model_config._BRIDGED_ENV_PAIRS:
        monkeypatch.setenv(src, f"value-from-{src}")
        monkeypatch.delenv(dst, raising=False)

    applied = model_config.bridge_author_env_to_experimentalist()

    assert applied == [dst for _, dst in model_config._BRIDGED_ENV_PAIRS]
    for src, dst in model_config._BRIDGED_ENV_PAIRS:
        assert os.environ[dst] == f"value-from-{src}"


def test_bridge_author_env_does_not_overwrite_existing_experimentalist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://experimentalist.example/v1")

    applied = model_config.bridge_author_env_to_experimentalist()

    assert applied == []
    assert os.environ["EXPERIMENTALIST_API_BASE"] == "https://experimentalist.example/v1"


def test_bridge_author_env_is_a_no_op_once_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTHOR_API_BASE", "https://eval-author.example/v1")
    monkeypatch.delenv("EXPERIMENTALIST_API_BASE", raising=False)

    assert model_config.bridge_author_env_to_experimentalist() == ["EXPERIMENTALIST_API_BASE"]
    assert model_config.bridge_author_env_to_experimentalist() == []


def test_agent_module_imports_under_author_credentials_alone() -> None:
    """Guard the import ordering that lets an AUTHOR_*-only run build Experimentalist agents.

    ``TraceAnalyzer`` and friends read ``EXPERIMENTALIST_*`` while their class body runs, so
    ``agent.py`` has to import ``_env_bridge`` before importing them. That ordering cannot be
    checked in-process: this test suite's conftest already populates ``EXPERIMENTALIST_*``,
    and the modules are imported once per session. Hence the subprocess with a pruned
    environment -- it fails with ``ValueError`` if the bridge stops running early enough.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AUTHOR_", "EXPERIMENTALIST_", "INFERENCE_API_KEY"))
    }
    env["AUTHOR_API_BASE"] = "https://placeholder.invalid"
    env["AUTHOR_API_KEY"] = "placeholder-for-import"

    result = subprocess.run(
        [sys.executable, "-c", "import nemo_eval_author_plugin.eval_author.agent"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
