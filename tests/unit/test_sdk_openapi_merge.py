# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Python SDK OpenAPI merge."""

from __future__ import annotations

import pytest

from script.generate_openapi_spec import merge_sdk_specs_strict


def _spec(path: str, schema: dict) -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "0.0.0"},
        "paths": {path: {"get": {"responses": {"200": {"description": "ok"}}}}},
        "components": {"schemas": {"Shared": schema}},
    }


def test_sdk_merge_keeps_identical_schema_collisions() -> None:
    schema = {"type": "object", "properties": {"id": {"type": "string"}}}

    merged = merge_sdk_specs_strict(
        [
            (_spec("/apis/platform/v1/items", schema), "openapi/openapi.yaml"),
            (_spec("/apis/intake/v2/items", schema), "plugins/nemo-intake/openapi/openapi.yaml"),
        ]
    )

    assert sorted(merged["paths"]) == ["/apis/intake/v2/items", "/apis/platform/v1/items"]
    assert merged["components"]["schemas"]["Shared"] == schema


def test_sdk_merge_errors_on_schema_collision() -> None:
    platform_schema = {"type": "object", "properties": {"id": {"type": "string"}}}
    plugin_schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

    with pytest.raises(ValueError, match="schema collision"):
        merge_sdk_specs_strict(
            [
                (_spec("/apis/platform/v1/items", platform_schema), "openapi/openapi.yaml"),
                (_spec("/apis/intake/v2/items", plugin_schema), "plugins/nemo-intake/openapi/openapi.yaml"),
            ]
        )


def test_sdk_merge_errors_on_path_collision() -> None:
    schema = {"type": "object"}

    with pytest.raises(ValueError, match="path collision"):
        merge_sdk_specs_strict(
            [
                (_spec("/apis/intake/v2/items", schema), "openapi/openapi.yaml"),
                (_spec("/apis/intake/v2/items", schema), "plugins/nemo-intake/openapi/openapi.yaml"),
            ]
        )
