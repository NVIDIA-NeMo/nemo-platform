# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Seed NMP with the workspace, providers, guardrail config, and VirtualModel
required by the IGW guardrails benchmark.

Replaces the previous ``setup_nmp_guardrails_benchmark.sh`` flow with direct
NMP SDK calls (``client.workspaces``, ``client.inference``, ``client.guardrail``).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from nemo_guardrails_plugin.benchmarks.constants import (
    APP_MODEL_NAME,
    APP_PROVIDER,
    APP_PROVIDER_URL,
    CS_MODEL_NAME,
    CS_PROVIDER,
    CS_PROVIDER_URL,
    GUARDRAIL_CONFIG,
    GUARDRAILS_MIDDLEWARE_CONFIG_TYPE,
    GUARDRAILS_MIDDLEWARE_NAME,
    VM_NAME,
    WORKSPACE,
)
from nemo_platform import NeMoPlatform, NotFoundError
from nemo_platform.types.inference.middleware_call_param import MiddlewareCallParam
from nemo_platform.types.inference.virtual_model_inference_config_param import (
    VirtualModelInferenceConfigParam,
)

log = logging.getLogger(__name__)

_PROVIDER_WAIT_TIMEOUT_SECONDS = 60
_PROVIDER_POLL_INTERVAL_SECONDS = 1.0


@dataclass(frozen=True)
class SeededResources:
    workspace: str
    app_provider_name: str
    cs_provider_name: str
    app_model_entity: str
    cs_model_entity: str
    guardrail_config_name: str
    vm_name: str

    @property
    def vm_ref(self) -> str:
        return f"{self.workspace}/{self.vm_name}"

    @property
    def guardrail_config_ref(self) -> str:
        return f"{self.workspace}/{self.guardrail_config_name}"


def seed_benchmark(
    client: NeMoPlatform,
    *,
    nemoguardrails_repo_root: Path,
    generated_dir: Path,
    provider_wait_timeout: float = _PROVIDER_WAIT_TIMEOUT_SECONDS,
) -> SeededResources:
    """Create workspace, providers, GuardrailConfig, and VirtualModel.

    All ``create`` calls are idempotent (``exist_ok=True``) so this is safe to
    rerun against a reused NMP instance.
    """
    generated_dir.mkdir(parents=True, exist_ok=True)

    log.info("Creating workspace %s", WORKSPACE)
    client.workspaces.create(
        name=WORKSPACE,
        description="Local IGW guardrails benchmark workspace",
        exist_ok=True,
    )

    log.info("Registering app mock provider %s", APP_PROVIDER)
    client.inference.providers.create(
        workspace=WORKSPACE,
        name=APP_PROVIDER,
        host_url=APP_PROVIDER_URL,
        enabled_models=[APP_MODEL_NAME],
        description=f"Benchmark mock app LLM on {APP_PROVIDER_URL}",
        exist_ok=True,
    )

    log.info("Registering content-safety mock provider %s", CS_PROVIDER)
    client.inference.providers.create(
        workspace=WORKSPACE,
        name=CS_PROVIDER,
        host_url=CS_PROVIDER_URL,
        enabled_models=[CS_MODEL_NAME],
        description=f"Benchmark mock content-safety LLM on {CS_PROVIDER_URL}",
        exist_ok=True,
    )

    log.info("Waiting for provider discovery")
    app_provider = _wait_for_served_model(
        client,
        provider_name=APP_PROVIDER,
        served_model_name=APP_MODEL_NAME,
        timeout_seconds=provider_wait_timeout,
    )
    cs_provider = _wait_for_served_model(
        client,
        provider_name=CS_PROVIDER,
        served_model_name=CS_MODEL_NAME,
        timeout_seconds=provider_wait_timeout,
    )

    app_entity = _extract_model_entity(app_provider, APP_MODEL_NAME, provider_name=APP_PROVIDER)
    cs_entity = _extract_model_entity(cs_provider, CS_MODEL_NAME, provider_name=CS_PROVIDER)

    _dump_model(generated_dir / "app_provider.json", app_provider)
    _dump_model(generated_dir / "content_safety_provider.json", cs_provider)

    log.info("Building GuardrailConfig payload from %s", nemoguardrails_repo_root)
    config_data = build_guardrail_config_data(
        source_config_dir=nemoguardrails_repo_root / "examples" / "configs" / "content_safety_local",
        content_safety_model_entity=cs_entity,
    )
    # Persist the same payload shape the old shell harness produced for debuggability.
    (generated_dir / "content_safety_local_nmp_request.json").write_text(
        json.dumps(
            {
                "name": GUARDRAIL_CONFIG,
                "description": "Benchmark content_safety_local config routed through IGW",
                "data": config_data,
                "exist_ok": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    log.info("Creating GuardrailConfig %s", GUARDRAIL_CONFIG)
    client.guardrail.configs.create(
        workspace=WORKSPACE,
        name=GUARDRAIL_CONFIG,
        description="Benchmark content_safety_local config routed through IGW",
        data=config_data,
        exist_ok=True,
    )

    middleware_call: MiddlewareCallParam = {
        "name": GUARDRAILS_MIDDLEWARE_NAME,
        "config_type": GUARDRAILS_MIDDLEWARE_CONFIG_TYPE,
        "config_id": f"{WORKSPACE}/{GUARDRAIL_CONFIG}",
    }
    vm_models: list[VirtualModelInferenceConfigParam] = [{"model": app_entity, "backend_format": "OPENAI_CHAT"}]

    log.info("Creating VirtualModel %s/%s", WORKSPACE, VM_NAME)
    vm = client.inference.virtual_models.create(
        workspace=WORKSPACE,
        name=VM_NAME,
        default_model_entity=app_entity,
        models=vm_models,
        request_middleware=[middleware_call],
        response_middleware=[middleware_call],
        exist_ok=True,
    )
    _dump_model(generated_dir / "virtual_model.json", vm)

    return SeededResources(
        workspace=WORKSPACE,
        app_provider_name=APP_PROVIDER,
        cs_provider_name=CS_PROVIDER,
        app_model_entity=app_entity,
        cs_model_entity=cs_entity,
        guardrail_config_name=GUARDRAIL_CONFIG,
        vm_name=VM_NAME,
    )


def _wait_for_served_model(
    client: NeMoPlatform,
    *,
    provider_name: str,
    served_model_name: str,
    timeout_seconds: float,
) -> Any:
    """Poll a provider until ``served_models`` lists the expected entry.

    Gateway readiness alone is not enough: VirtualModel creation needs the
    discovered ``model_entity_id``, which only appears once the provider has
    enumerated its models.
    """
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            provider = client.inference.providers.retrieve(provider_name, workspace=WORKSPACE)
        except NotFoundError as exc:
            last_error = exc
            time.sleep(_PROVIDER_POLL_INTERVAL_SECONDS)
            continue
        served_models = getattr(provider, "served_models", None) or []
        for m in served_models:
            if getattr(m, "served_model_name", None) == served_model_name and getattr(m, "model_entity_id", None):
                return provider
        time.sleep(_PROVIDER_POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"Provider {provider_name!r} did not surface served model "
        f"{served_model_name!r} within {timeout_seconds}s: {last_error}"
    )


def _extract_model_entity(provider: Any, served_model_name: str, *, provider_name: str) -> str:
    for m in getattr(provider, "served_models", None) or []:
        if getattr(m, "served_model_name", None) == served_model_name:
            entity = getattr(m, "model_entity_id", None)
            if entity:
                return entity
    raise RuntimeError(f"Provider {provider_name!r} does not expose served model {served_model_name!r}")


def build_guardrail_config_data(
    *,
    source_config_dir: Path,
    content_safety_model_entity: str,
) -> dict[str, Any]:
    """Read the upstream content_safety_local config and rewrite it for NMP.

    The upstream config references an HTTP base_url; in NMP we instead route by
    ``model_entity_id`` resolved via the inference gateway. Prompts are inlined
    from the sibling ``prompts.yml`` file.
    """
    config_yaml = source_config_dir / "config.yml"
    prompts_yaml = source_config_dir / "prompts.yml"
    if not config_yaml.is_file():
        raise FileNotFoundError(f"Expected guardrails config at {config_yaml}")
    if not prompts_yaml.is_file():
        raise FileNotFoundError(f"Expected guardrails prompts at {prompts_yaml}")

    config = yaml.safe_load(config_yaml.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected a YAML mapping at {config_yaml}, got {type(config).__name__}")

    prompts = yaml.safe_load(prompts_yaml.read_text(encoding="utf-8")) or {}
    if not isinstance(prompts, dict):
        raise ValueError(f"Expected a YAML mapping at {prompts_yaml}, got {type(prompts).__name__}")

    config["models"] = [
        {
            "type": "content_safety",
            "engine": "nim",
            "model": content_safety_model_entity,
        }
    ]
    config["prompts"] = prompts.get("prompts", [])
    return config


def _dump_model(path: Path, model: Any) -> None:
    """Best-effort serialize an SDK response model to JSON."""
    if hasattr(model, "model_dump"):
        payload = model.model_dump(mode="json")
    elif hasattr(model, "to_dict"):
        payload = model.to_dict()
    else:
        payload = json.loads(json.dumps(model, default=str))
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
