# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Body serialization contract for VirtualModel CRUD endpoints.

Paths, methods, and response types are proven against the real IGW router in
``services/core/inference-gateway/tests/unit/test_virtual_models_router.py``;
endpoint decorator mechanics are covered in ``tests/client/test_endpoint.py``.
This file pins the serialization rules a request body must obey, which neither
of those can observe.
"""

from __future__ import annotations

import json

from nemo_platform_plugin.client.types import PreparedRequest
from nemo_platform_plugin.virtual_models import endpoints
from nemo_platform_plugin.virtual_models.types import (
    CreateVirtualModelRequest,
    UpdateVirtualModelRequest,
    VirtualModelInferenceConfig,
)


def _json_body(prepared: PreparedRequest) -> dict[str, object]:
    assert isinstance(prepared.content, bytes)
    return json.loads(prepared.content)


def test_create_omits_unset_fields_and_nested_nones() -> None:
    """Defaults stay off the wire so the server applies its own."""
    body = CreateVirtualModelRequest(
        name="router",
        default_model_entity="default/llama",
        models=[VirtualModelInferenceConfig(model="default/llama")],
    )

    prepared = endpoints.create_virtual_model(workspace="default", body=body)

    assert prepared.content_type == "application/json"
    assert _json_body(prepared) == {
        "name": "router",
        "default_model_entity": "default/llama",
        "models": [{"model": "default/llama"}],
    }


def test_update_distinguishes_explicit_null_and_empty_list_from_unset() -> None:
    """PATCH must send only what the caller set, so omitted fields stay unchanged."""
    body = UpdateVirtualModelRequest(default_model_entity=None, request_middleware=[])

    prepared = endpoints.update_virtual_model(workspace="default", name="router", body=body)

    assert _json_body(prepared) == {"default_model_entity": None, "request_middleware": []}
