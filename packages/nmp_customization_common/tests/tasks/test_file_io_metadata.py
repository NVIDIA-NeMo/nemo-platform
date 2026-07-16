# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for output fileset metadata helpers."""

from types import SimpleNamespace

from nmp.customization_common.tasks.file_io_metadata import (
    build_model_fileset_metadata,
    build_output_fileset_metadata_from_model_entity,
    extract_tool_calling_metadata,
)


class TestBuildModelFilesetMetadata:
    def test_wraps_tool_calling_under_model(self) -> None:
        meta = build_model_fileset_metadata(tool_calling={"tool_call_parser": "llama3_json"})
        assert meta == {"model": {"tool_calling": {"tool_call_parser": "llama3_json"}}}

    def test_returns_none_when_empty(self) -> None:
        assert build_model_fileset_metadata(tool_calling=None) is None


class TestExtractToolCallingMetadata:
    def test_extracts_from_model_entity_spec(self) -> None:
        me = SimpleNamespace(
            spec=SimpleNamespace(
                chat_template="{% for m in messages %}{{ m }}{% endfor %}",
                tool_call_config=SimpleNamespace(
                    tool_call_parser="llama3_json",
                    tool_call_plugin="default/plugin-fs",
                    auto_tool_choice=True,
                ),
            ),
        )
        assert extract_tool_calling_metadata(me) == {
            "chat_template": "{% for m in messages %}{{ m }}{% endfor %}",
            "tool_call_parser": "llama3_json",
            "tool_call_plugin": "default/plugin-fs",
            "auto_tool_choice": True,
        }

    def test_returns_none_without_spec(self) -> None:
        assert extract_tool_calling_metadata(SimpleNamespace(spec=None)) is None


class TestBuildOutputFilesetMetadataFromModelEntity:
    def test_builds_nested_model_metadata(self) -> None:
        me = SimpleNamespace(
            spec=SimpleNamespace(
                chat_template=None,
                tool_call_config=SimpleNamespace(
                    tool_call_parser="hermes",
                    tool_call_plugin=None,
                    auto_tool_choice=None,
                ),
            ),
        )
        assert build_output_fileset_metadata_from_model_entity(me) == {
            "model": {"tool_calling": {"tool_call_parser": "hermes"}},
        }
