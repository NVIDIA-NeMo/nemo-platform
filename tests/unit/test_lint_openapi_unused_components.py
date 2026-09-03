# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from script.lint_openapi_unused_components import UnusedComponent, find_unused_components, main


def _ref(component_type: str, name: str) -> dict[str, str]:
    return {"$ref": f"#/components/{component_type}/{name}"}


def test_find_unused_components_keeps_schema_referenced_directly_from_response() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/apis/widgets/v2/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {"application/json": {"schema": _ref("schemas", "Widget")}},
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Widget": {"type": "object"},
            }
        },
    }

    assert find_unused_components(spec) == []


def test_find_unused_components_decodes_percent_encoded_component_ref() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/apis/widgets/v2/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {"application/json": {"schema": _ref("schemas", "Widget%20Config")}},
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Widget Config": {"type": "object"},
            }
        },
    }

    assert find_unused_components(spec) == []


def test_find_unused_components_keeps_nested_schema_dependencies() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/apis/widgets/v2/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": _ref("schemas", "WidgetPage"),
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "WidgetPage": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "array",
                            "items": _ref("schemas", "Widget"),
                        }
                    },
                },
                "Widget": {"type": "object"},
            }
        },
    }

    assert find_unused_components(spec) == []


def test_find_unused_components_reports_unused_schema_chain() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/apis/widgets/v2/widgets": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": _ref("schemas", "Widget"),
                                }
                            },
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "Widget": {"type": "object"},
                "Orphan": {
                    "type": "object",
                    "properties": {"child": _ref("schemas", "OrphanChild")},
                },
                "OrphanChild": {"type": "object"},
            }
        },
    }

    assert find_unused_components(spec) == [
        UnusedComponent(section="schemas", name="Orphan"),
        UnusedComponent(section="schemas", name="OrphanChild"),
    ]


def test_find_unused_components_follows_referenced_request_body_response_and_parameter() -> None:
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/apis/widgets/v2/widgets/{name}": {
                "parameters": [_ref("parameters", "Workspace")],
                "post": {
                    "parameters": [_ref("parameters", "Name")],
                    "requestBody": _ref("requestBodies", "WidgetCreateBody"),
                    "responses": {"200": _ref("responses", "WidgetResponse")},
                },
            }
        },
        "components": {
            "parameters": {
                "Workspace": {
                    "name": "workspace",
                    "in": "path",
                    "schema": {"type": "string"},
                },
                "Name": {
                    "name": "name",
                    "in": "path",
                    "schema": {"type": "string"},
                },
            },
            "requestBodies": {
                "WidgetCreateBody": {"content": {"application/json": {"schema": _ref("schemas", "WidgetCreate")}}}
            },
            "responses": {
                "WidgetResponse": {
                    "description": "OK",
                    "content": {"application/json": {"schema": _ref("schemas", "Widget")}},
                }
            },
            "schemas": {
                "WidgetCreate": {"type": "object"},
                "Widget": {"type": "object"},
            },
        },
    }

    assert find_unused_components(spec) == []


def test_find_unused_components_marks_security_schemes_from_security_requirements() -> None:
    spec = {
        "openapi": "3.1.0",
        "security": [{"BearerAuth": []}],
        "paths": {"/apis/widgets/v2/widgets": {"get": {"responses": {"204": {"description": "No content"}}}}},
        "components": {
            "securitySchemes": {
                "BearerAuth": {"type": "http", "scheme": "bearer"},
                "UnusedAuth": {"type": "apiKey", "name": "x-unused", "in": "header"},
            }
        },
    }

    assert find_unused_components(spec) == [UnusedComponent(section="securitySchemes", name="UnusedAuth")]


def test_main_reports_unused_components_sorted(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    spec_path = tmp_path / "openapi.yaml"
    spec_path.write_text(
        textwrap.dedent(
            """
            openapi: 3.1.0
            paths:
              /apis/widgets/v2/widgets:
                get:
                  responses:
                    "204":
                      description: No content
            components:
              schemas:
                Zebra:
                  type: object
                Alpha:
                  type: object
            """
        )
    )

    exit_code = main([str(spec_path)])
    output = capsys.readouterr()

    assert exit_code == 1
    assert output.err.splitlines() == [
        f"{spec_path}: unused OpenAPI components:",
        "  - components.schemas.Alpha",
        "  - components.schemas.Zebra",
    ]
