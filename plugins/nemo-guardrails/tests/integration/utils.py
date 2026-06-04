# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Common functions shared by the nemo-guardrails plugin integration tests.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from nemo_guardrails_plugin.constants import GUARDRAILS_PLUGIN_CONFIG_TYPE
from nemo_platform.types.guardrail import GuardrailConfig
from nemo_platform.types.inference.middleware_call_param import MiddlewareCallParam
from nmp.testing.utils import short_unique_name

DEFAULT_WORKSPACE = "default"
"""Default workspace seeded by the module-scoped IGW fixture. Helpers
default to this so parametrise-time builders that don't have a harness
yet keep working; production test bodies pass ``harness.workspace``
explicitly so the helpers stay portable if the fixture ever moves to
per-test workspaces."""

GUARDRAILS_PLUGIN_NAME = "nemo-guardrails"


@dataclass(frozen=True)
class ServedModel:
    served_name: str
    entity_ref: str


@dataclass(frozen=True)
class GuardrailsTestDataNames:
    test_id: str
    main_model_served_name: str
    main_model_entity_ref: str
    request_virtual_model_name: str
    guardrail_config_name: str
    model_provider_name: str


def make_served_model(
    *,
    test_id: str,
    prefix: str,
    workspace: str = DEFAULT_WORKSPACE,
) -> ServedModel:
    served_name = f"{prefix}-{test_id}"
    return ServedModel(served_name=served_name, entity_ref=f"{workspace}/{served_name}")


def make_guardrails_test_data_names(
    *,
    main_model_prefix: str = "main-model",
    workspace: str = DEFAULT_WORKSPACE,
) -> GuardrailsTestDataNames:
    """Build a unique set of names + entity refs for one test.

    Pass ``workspace=harness.workspace`` so ``main_model_entity_ref``
    lines up with the harness's workspace. The default is a safety
    net for parametrise-time callers without a harness in scope.
    """
    test_id = short_unique_name("test")
    main_model = make_served_model(test_id=test_id, prefix=main_model_prefix, workspace=workspace)
    return GuardrailsTestDataNames(
        test_id=test_id,
        main_model_served_name=main_model.served_name,
        main_model_entity_ref=main_model.entity_ref,
        request_virtual_model_name=f"gr-vm-{test_id}",
        guardrail_config_name=f"gr-config-{test_id}",
        model_provider_name=f"gr-provider-{test_id}",
    )


class RailType(str, Enum):
    """The rail directions a guardrail config can declare.

    Used by per-class ``_config_data`` builders to select which rail
    flows and prompts are wired into the generated config.
    """

    INPUT = "input"
    OUTPUT = "output"


def make_guardrail_config(
    workspace: str,
    name: str,
    *,
    data: dict[str, Any],
) -> GuardrailConfig:
    """Wrap a ``data`` block (the inner PlatformRailsConfig shape) in a GuardrailConfig envelope.

    The envelope (``id`` / ``entity_id`` / ``parent`` / timestamps) is
    irrelevant to plugin behaviour but required by the SDK type.
    """
    return GuardrailConfig.model_validate(
        {
            "id": f"{workspace}/{name}",
            "entity_id": f"{workspace}/{name}",
            "parent": workspace,
            "workspace": workspace,
            "name": name,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "data": data,
        }
    )


def make_middleware_call(config: GuardrailConfig) -> MiddlewareCallParam:
    # validate_middleware_config expects the inner PlatformRailsConfig data
    # block (models / rails / prompts), not the entity envelope. The full
    # GuardrailConfig dump silently absorbs envelope fields into model_extra
    # and rails.rails ends up None, so the plugin's input rail gets bypassed.
    if config.data is None:
        raise ValueError("GuardrailConfig.data is required for inline middleware calls.")

    payload = config.data.model_dump(mode="json", exclude_none=True)

    # Thread the config name through as the inline diagnostic label so
    # log lines and the response's guardrails_data carry ``<inline:<name>>``
    # instead of the bare ``<inline>`` placeholder.
    if config.name:
        payload["name"] = config.name

    return {
        "name": GUARDRAILS_PLUGIN_NAME,
        "config_type": GUARDRAILS_PLUGIN_CONFIG_TYPE,
        "config": payload,
    }
