# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from nemo_platform_sdk_tools.sdk.core.openapi import OpenAPI
from nemo_platform_sdk_tools.sdk.core.stainless import StainlessConfig
from nemo_platform_sdk_tools.sdk.openapi_stainless_mapper import SchemaMapper
from nemo_platform_sdk_tools.sdk.source_owned_resources import SOURCE_OWNED_RESOURCE_EXCLUSIONS, SourceOwnedResource

WIDGETS = SourceOwnedResource(resource_name="widgets", path_prefixes=("/apis/widgets/v2",))
JOBS = SourceOwnedResource(resource_name="jobs", path_prefixes=("/apis/jobs/v2",))


def _schema_ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/components/schemas/{name}"}


def _json_response(schema_name: str) -> dict[str, object]:
    return {
        "description": "OK",
        "content": {
            "application/json": {
                "schema": _schema_ref(schema_name),
            }
        },
    }


def _openapi_spec() -> OpenAPI:
    return OpenAPI(
        {
            "openapi": "3.1.0",
            "paths": {
                "/apis/widgets/v2/workspaces/{workspace}/widgets": {
                    "get": {
                        "responses": {
                            "200": _json_response("WidgetPage"),
                        }
                    },
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": _schema_ref("WidgetCreateRequest"),
                                }
                            }
                        },
                        "responses": {
                            "200": _json_response("WidgetResponse"),
                        },
                    },
                },
                "/apis/widgets/v2/workspaces/{workspace}/widgets/{name}/logs": {
                    "get": {
                        "responses": {
                            "200": _json_response("SharedLogPage"),
                        }
                    }
                },
                "/apis/files/v2/workspaces/{workspace}/files/{name}/logs": {
                    "get": {
                        "responses": {
                            "200": _json_response("SharedLogPage"),
                        }
                    }
                },
                "/apis/gadgets/v2/workspaces/{workspace}/gadgets": {
                    "get": {
                        "responses": {
                            "200": _json_response("GadgetPage"),
                        }
                    }
                },
            },
            "components": {
                "schemas": {
                    "WidgetCreateRequest": {
                        "type": "object",
                        "properties": {
                            "runtime": _schema_ref("WidgetRuntime"),
                        },
                    },
                    "WidgetRuntime": {"type": "object"},
                    "WidgetResponse": {"type": "object"},
                    "WidgetPage": {"type": "object"},
                    "SharedLog": {"type": "object"},
                    "SharedLogPage": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "array",
                                "items": _schema_ref("SharedLog"),
                            }
                        },
                    },
                    "GadgetPage": {"type": "object"},
                }
            },
        }
    )


def _stainless_config_without_widgets() -> StainlessConfig:
    return StainlessConfig(
        {
            "resources": {
                "$shared": {
                    "models": {
                        "shared_log": "SharedLog",
                        "shared_log_page": "SharedLogPage",
                    }
                }
            }
        }
    )


def _stainless_config_with_widgets() -> StainlessConfig:
    return StainlessConfig(
        {
            "resources": {
                "widgets": {
                    "standalone_api": True,
                    "methods": {},
                },
                "$shared": {
                    "models": {
                        "shared_log": "SharedLog",
                        "shared_log_page": "SharedLogPage",
                    }
                },
            }
        }
    )


def test_default_source_owned_resource_registry_contains_jobs() -> None:
    assert JOBS in SOURCE_OWNED_RESOURCE_EXCLUSIONS


def test_sync_methods_skips_source_owned_resource_when_resource_is_absent() -> None:
    stainless_config = _stainless_config_without_widgets()
    mapper = SchemaMapper(_openapi_spec(), stainless_config, source_owned_resources=(WIDGETS,))

    assert mapper.sync_endpoints_with_methods() is True

    methods = stainless_config.extract_methods()
    assert all(not method.endpoint.path.startswith("/apis/widgets/v2") for method in methods)
    assert any(
        method.endpoint.path == "/apis/gadgets/v2/workspaces/{workspace}/gadgets"
        and method.method_name.startswith("reviewme_")
        for method in methods
    )


def test_sync_models_derives_source_owned_schemas_from_excluded_endpoint_usage() -> None:
    stainless_config = _stainless_config_without_widgets()
    mapper = SchemaMapper(_openapi_spec(), stainless_config, source_owned_resources=(WIDGETS,))

    assert mapper.sync_schemas_with_models() is True

    schema_names = {model.schema_name for model in stainless_config.extract_models()}
    assert "WidgetCreateRequest" not in schema_names
    assert "WidgetRuntime" not in schema_names
    assert "WidgetResponse" not in schema_names
    assert "WidgetPage" not in schema_names
    assert "SharedLog" in schema_names
    assert "SharedLogPage" in schema_names
    assert "GadgetPage" in schema_names


def test_source_owned_sync_exclusion_is_inactive_when_resource_exists() -> None:
    stainless_config = _stainless_config_with_widgets()
    mapper = SchemaMapper(_openapi_spec(), stainless_config, source_owned_resources=(WIDGETS,))

    assert mapper.sync_endpoints_with_methods() is True

    methods = stainless_config.extract_methods()
    assert any(method.endpoint.path.startswith("/apis/widgets/v2") for method in methods)
