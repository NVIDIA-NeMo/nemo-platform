# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for user-selectable model configuration: env mapping, merge, and victim-model rewrite."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from _doubles import make_entity, make_job_context, make_sdk
from nemo_iron_swarm_plugin.agent_resolver import inject_gateway_url
from nemo_iron_swarm_plugin.jobs import _common
from nemo_iron_swarm_plugin.jobs import run as run_module
from nemo_iron_swarm_plugin.model_config import ModelChoice, WarGameModels


class _FakeSecrets:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def access(self, name: str, *, workspace: str) -> Any:
        return SimpleNamespace(value=self._values.get(name))


def _sdk(secrets: dict[str, str]) -> Any:
    return SimpleNamespace(secrets=_FakeSecrets(secrets))


def test_build_model_env_maps_attack_and_analysis_groups() -> None:
    models = WarGameModels(
        attack=ModelChoice(model="atk/model", base_url="https://atk/v1", api_key_secret="atk-key"),
        analysis=ModelChoice(model="ana/model", base_url="https://ana/v1", api_key_secret="ana-key"),
    )
    env = _common.build_model_env(models, sdk=_sdk({"atk-key": "AK", "ana-key": "NK"}), workspace="default")
    assert env["GARAK_RED_TEAM_MODEL_NAME"] == "atk/model"
    assert env["GARAK_DETECTOR_MODEL_NAME"] == "atk/model"
    assert env["GARAK_RED_TEAM_MODEL_URI"] == "https://atk/v1"
    assert env["GARAK_DETECTOR_MODEL_URI"] == "https://atk/v1"
    assert env["NIM_API_KEY"] == "AK"
    assert env["IRON_SWARM_MODEL"] == "ana/model"
    assert env["IRON_SWARM_BASE_URL"] == "https://ana/v1"
    assert env["INFERENCE_API_KEY"] == "NK"


def test_build_model_env_skips_unset_fields_and_safety_group() -> None:
    # Only a model name for analysis; no base_url/secret. Safety is never an env knob — it travels in
    # the manifest, as the guardrails defender entry's `config`.
    models = WarGameModels(analysis=ModelChoice(model="ana/model"), safety=ModelChoice(model="guard/model"))
    env = _common.build_model_env(models, sdk=_sdk({}), workspace="default")
    assert env == {"IRON_SWARM_MODEL": "ana/model"}


def test_build_model_env_none_is_empty() -> None:
    assert _common.build_model_env(None, sdk=_sdk({}), workspace="default") == {}


def test_effective_models_merges_override_over_stored_default(tmp_path: Path) -> None:
    stored = {"attack": {"model": "stored/atk", "base_url": "https://stored/v1"}}
    sdk = make_sdk(SimpleNamespace(get_entity_by_name=lambda **_k: make_entity(models=stored)))
    config = {"manifest_id": "m1", "models": {"attack": {"model": "override/atk"}, "analysis": {"model": "ana"}}}
    merged = run_module._effective_models(sdk, config, ctx=make_job_context(tmp_path))
    assert merged is not None
    # override wins per field; the stored base_url is preserved where the override left it unset.
    assert merged.attack is not None and merged.attack.model == "override/atk"
    assert merged.attack.base_url == "https://stored/v1"
    assert merged.analysis is not None and merged.analysis.model == "ana"


def test_effective_models_none_when_nothing_selected(tmp_path: Path) -> None:
    sdk = make_sdk(SimpleNamespace(get_entity_by_name=lambda **_k: make_entity()))
    config = {"manifest_id": "m1"}
    assert run_module._effective_models(sdk, config, ctx=make_job_context(tmp_path)) is None


def test_inject_gateway_url_never_rewrites_the_victims_model() -> None:
    """The victim's LLM is the target under test; the war-game binds its endpoint, never its model."""
    config = {"llms": {"main": {"_type": "openai", "model": "orig"}, "other": {"_type": "nim", "model": "orig2"}}}
    injected = inject_gateway_url(config, "default", "https://gw")
    assert injected["llms"]["main"]["model"] == "orig"
    assert injected["llms"]["other"]["model"] == "orig2"
    # base_url/api_key are still gateway-bound.
    assert "/apis/inference-gateway/" in injected["llms"]["main"]["base_url"]
    assert injected["llms"]["main"]["api_key"] == "not-used"
