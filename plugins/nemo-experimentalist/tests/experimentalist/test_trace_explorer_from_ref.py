# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for TraceExplorer.from_ref intake:// URI parsing.

Trial/eval traces are persisted as ``intake://traces/<id>`` while Eval Author traces
attached to an Insight use the bare ``intake://<id>`` form. ``from_ref`` must resolve both to the
raw ``<id>`` that Intake filters on — otherwise trial traces query ClickHouse
with a ``traces/<id>`` id that never matches and are silently skipped, even once
the platform client/workspace are correctly plumbed in.
"""

import json
from typing import Any, cast

import pytest
from nemo_experimentalist_plugin.entities import ResourceRef
from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import TraceExplorer


@pytest.fixture
def capture_from_intake(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Replace TraceExplorer.from_intake with a recorder; return the call log."""
    calls: list[dict[str, Any]] = []

    async def _fake_from_intake(cls: Any, client: Any, trace_id: str, *, workspace: str, **kwargs: Any) -> str:
        calls.append({"client": client, "trace_id": trace_id, "workspace": workspace})
        return "sentinel-trace-explorer"

    monkeypatch.setattr(TraceExplorer, "from_intake", classmethod(_fake_from_intake))
    return calls


@pytest.mark.asyncio
async def test_from_ref_strips_traces_prefix_for_trial_traces(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """``intake://traces/<id>`` (trial-trace format) resolves to the bare <id>."""
    client = cast(Any, object())
    ref = ResourceRef(uri="intake://traces/abc123")

    result = await TraceExplorer.from_ref(ref, client, "ws-1")

    assert result == "sentinel-trace-explorer"
    assert capture_from_intake == [{"client": client, "trace_id": "abc123", "workspace": "ws-1"}]


@pytest.mark.asyncio
async def test_from_ref_handles_bare_intake_uri_for_eval_author_traces(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """``intake://<id>`` (Eval Author Insight format) still resolves to <id>."""
    client = cast(Any, object())
    ref = ResourceRef(uri="intake://abc123")

    await TraceExplorer.from_ref(ref, client, "ws-1")

    assert capture_from_intake == [{"client": client, "trace_id": "abc123", "workspace": "ws-1"}]


@pytest.mark.asyncio
async def test_from_ref_requires_client_and_workspace(
    capture_from_intake: list[dict[str, Any]],
) -> None:
    """Without client/workspace, intake refs raise rather than being silently skipped."""
    ref = ResourceRef(uri="intake://traces/abc123")

    with pytest.raises(ValueError, match="missing client/workspace"):
        await TraceExplorer.from_ref(ref, None, None)

    assert capture_from_intake == []


# ---------------------------------------------------------------------------
# backend-specific parsing
# ---------------------------------------------------------------------------


def _intake_llm_row(**overrides):
    row = {
        "span_id": "span-1",
        "trace_id": "trace-1",
        "source": "atif",
        "kind": "LLM",
        "name": "agent-step",
        "model": "provider/model",
        "input_tokens": 25773,
        "output_tokens": 131,
        "input": "book me a flight",
        "output": "booked",
        "raw_attributes": json.dumps({"source": "agent", "message": "booked", "step_id": 2}),
    }
    row.update(overrides)
    return row


def test_intake_row_reads_token_counts_from_columns():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    span = _span_from_intake_row(_intake_llm_row())
    assert span.token_counts == {"prompt": 25773, "completion": 131}


def test_intake_row_reads_all_four_token_columns():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(cached_tokens=8, total_tokens=25904)
    span = _span_from_intake_row(row)
    assert span.token_counts == {
        "prompt": 25773,
        "completion": 131,
        "cached": 8,
        "total": 25904,
    }


def test_intake_row_ignores_absent_token_columns():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row()
    del row["input_tokens"]
    span = _span_from_intake_row(row)
    assert span.token_counts == {"completion": 131}


def test_intake_row_reads_model_and_payloads_from_columns():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    span = _span_from_intake_row(_intake_llm_row())
    assert span.model_name == "provider/model"
    assert span.input_value == "book me a flight"
    assert span.output_value == "booked"


def test_intake_atif_row_synthesizes_output_messages():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    span = _span_from_intake_row(_intake_llm_row())
    assert [message.role for message in span.output_messages] == ["assistant"]
    assert span.output_messages[0].content == "booked"


def test_intake_atif_row_synthesizes_input_messages_for_user_steps():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(
        raw_attributes=json.dumps({"source": "user", "message": "book me a flight", "step_id": 1}),
        output="",
    )
    span = _span_from_intake_row(row)
    assert [message.role for message in span.input_messages] == ["user"]
    assert span.output_messages == []


def test_intake_otlp_row_does_not_synthesize_messages():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    # source='otlp' means the ATIF branch must not fire, even if the bag happens
    # to carry a message-shaped key.
    row = _intake_llm_row(source="otlp")
    span = _span_from_intake_row(row)
    assert span.output_messages == []


def test_intake_tool_row_reads_the_preserved_tool_call_id():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(
        kind="TOOL",
        tool_name="Bash",
        raw_attributes=json.dumps({"tool_call": {"tool_call_id": "c1", "function_name": "Bash"}}),
    )
    span = _span_from_intake_row(row)
    assert span.tool_name == "Bash"
    assert span.tool_call_id == "c1"


def test_intake_otlp_tool_row_keeps_its_attribute_tool_call_id():
    # tool_call_id has no Intake column, so OTLP rows carry it in raw_attributes.
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(
        source="otlp",
        kind="TOOL",
        tool_name="Bash",
        raw_attributes=json.dumps({"tool_call.id": "call_otlp_1"}),
    )
    span = _span_from_intake_row(row)
    assert span.tool_call_id == "call_otlp_1"


def test_intake_row_reads_error_fields_from_columns():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(kind="TOOL", error_type="TimeoutError", error_message="tool timed out")
    span = _span_from_intake_row(row)
    assert span.error_type == "TimeoutError"
    assert span.error_message == "tool timed out"


def test_intake_row_reads_tool_definitions_from_the_agent_block():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(
        raw_attributes=json.dumps({"agent": {"tool_definitions": [{"name": "Bash", "description": "run a command"}]}})
    )
    span = _span_from_intake_row(row)
    assert [tool.name for tool in span.tools] == ["Bash"]


def test_intake_row_preserves_parent_and_kind():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_intake_row

    row = _intake_llm_row(kind="AGENT", parent_span_id="span-0", agent_name="Codeact")
    span = _span_from_intake_row(row)
    assert span.kind == "AGENT"
    assert span.parent_span_id == "span-0"
    assert span.agent_name == "Codeact"


def test_otlp_record_still_reads_token_counts_from_attributes():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _span_from_otlp_record

    record = {
        "spanId": "abc",
        "traceId": "def",
        "name": "llm",
        "attributes": {
            "openinference.span.kind": "LLM",
            "llm.token_count.prompt": 100,
            "llm.token_count.completion": 20,
        },
    }
    span = _span_from_otlp_record(record)
    assert span.token_counts == {"prompt": 100, "completion": 20}


def test_intake_shaped_records_in_a_file_route_to_the_intake_parser():
    from nemo_experimentalist_plugin.experimentalist.components.trace_explorer import _looks_like_intake_row

    assert _looks_like_intake_row(_intake_llm_row()) is True
    assert _looks_like_intake_row({"spanId": "abc", "attributes": {}}) is False


async def test_from_ref_explains_why_a_local_atif_trajectory_cannot_be_read(tmp_path):
    path = tmp_path / "trajectory-abc123.atif.json"
    path.write_text('{"schema_version": "ATIF-v1.7", "session_id": "abc123"}', encoding="utf-8")
    ref = ResourceRef(uri=f"file://{path}", description="", metadata={"trace_format": "atif"})

    with pytest.raises(ValueError, match="never uploaded"):
        await TraceExplorer.from_ref(ref)


async def test_from_ref_still_reads_a_local_otlp_jsonl(tmp_path):
    span = {
        "spanId": "abc",
        "traceId": "def",
        "name": "llm",
        "attributes": {"openinference.span.kind": "LLM"},
    }
    path = tmp_path / "trace.jsonl"
    path.write_text(json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [span]}]}]}) + "\n", encoding="utf-8")
    ref = ResourceRef(uri=f"file://{path}", description="", metadata={"trace_format": "otlp"})

    explorer = await TraceExplorer.from_ref(ref)
    assert explorer is not None
