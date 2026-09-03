# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from typing import Any

import pytest
from nemo_evaluator_sdk.values.otlp import (
    export_request_from_resource_spans,
    final_output_text,
    resource_spans_from_text,
    span_text_strings,
)

_TRACE_ID = "0" * 32


def _span(
    span_id: str, *, end: int, parent: str | None = None, kind: str = "AGENT", **attributes: str
) -> dict[str, Any]:
    attributes = {"openinference.span.kind": kind, **attributes}
    span: dict[str, Any] = {
        "traceId": _TRACE_ID,
        "spanId": span_id,
        "name": f"span-{span_id}",
        "startTimeUnixNano": "1",
        "endTimeUnixNano": str(end),
        "attributes": [{"key": key, "value": {"stringValue": value}} for key, value in attributes.items()],
    }
    if parent is not None:
        span["parentSpanId"] = parent
    return span


def _answer(*spans: dict[str, Any]) -> str | None:
    return final_output_text(export_request_from_resource_spans([{"scopeSpans": [{"spans": list(spans)}]}]))


def _messages(text: str) -> str:
    return json.dumps([{"role": "assistant", "parts": [{"type": "text", "content": text}]}])


def test_root_span_output_is_the_answer_even_when_a_child_ends_later() -> None:
    answer = _answer(
        _span("a" * 16, end=5, **{"output.value": "final answer"}),
        _span("b" * 16, end=99, parent="a" * 16, **{"output.value": "intermediate"}),
    )

    assert answer == "final answer"


def test_a_tool_result_never_becomes_the_answer() -> None:
    # gen_ai.tool.call.result is in Intake's payload list but not this one: a tool's output
    # is not the model's, and this value is compared against a reference by content metrics.
    answer = _answer(
        _span("a" * 16, end=5),
        _span("b" * 16, end=99, parent="a" * 16, **{"gen_ai.tool.call.result": "TOOL OUTPUT"}),
    )

    assert answer is None


def test_latest_ending_span_answers_when_the_root_carries_no_output() -> None:
    answer = _answer(
        _span("a" * 16, end=1),
        _span("b" * 16, end=5, parent="a" * 16, **{"output.value": "earlier"}),
        _span("c" * 16, end=9, parent="a" * 16, **{"output.value": "latest"}),
    )

    assert answer == "latest"


def test_assistant_text_is_extracted_from_the_semantic_convention_payload() -> None:
    answer = _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": _messages("extracted")}))

    assert answer == "extracted"


def test_the_last_assistant_message_wins_within_one_payload() -> None:
    payload = json.dumps(
        [
            {"role": "assistant", "parts": [{"type": "text", "content": "first"}]},
            {"role": "user", "parts": [{"type": "text", "content": "ignored"}]},
            {"role": "assistant", "parts": [{"type": "text", "content": "second"}]},
        ]
    )

    assert _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": payload})) == "second"


def test_a_plain_text_message_payload_is_the_answer() -> None:
    # Not JSON at all is the one case where the raw value is plausibly the answer itself.
    assert _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": "not json at all"})) == "not json at all"


@pytest.mark.parametrize("payload", ['{"not": "a list"}', "[]", '[{"role": "user", "parts": []}]'])
def test_structured_payloads_without_assistant_text_yield_no_answer(payload: str) -> None:
    # Returning the raw JSON here would score serialized telemetry, and would look truthy to
    # the caller so the ATIF fallback never runs.
    assert _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": payload})) is None


def test_a_later_key_answers_when_the_message_payload_carries_no_text() -> None:
    answer = _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": "[]", "final_result": "typed result"}))

    assert answer == "typed result"


def test_key_precedence_prefers_output_value_over_the_message_payload() -> None:
    answer = _answer(
        _span(
            "a" * 16,
            end=5,
            **{"output.value": "winner", "gen_ai.output.messages": _messages("loser")},
        )
    )

    assert answer == "winner"


def test_no_output_attribute_anywhere_yields_no_answer() -> None:
    assert _answer(_span("a" * 16, end=5), _span("b" * 16, end=9, parent="a" * 16)) is None


def test_jsonl_requests_are_concatenated_in_file_order() -> None:
    raw = "\n".join(
        json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": [_span(char * 16, end=index)]}]}]})
        for index, char in enumerate("ab", start=1)
    )

    assert len(resource_spans_from_text(raw)) == 2


def test_blank_text_has_no_resource_spans() -> None:
    assert resource_spans_from_text("   \n") == []


def test_a_malformed_jsonl_line_is_reported_with_its_line_number() -> None:
    raw = '{"resourceSpans": []}\n{oops\n'

    with pytest.raises(ValueError, match="line 2"):
        resource_spans_from_text(raw)


def test_a_request_without_resource_spans_is_rejected() -> None:
    with pytest.raises(ValueError, match="requires a resourceSpans list"):
        resource_spans_from_text('{"other": []}')


def test_a_payload_that_is_not_otlp_is_rejected_as_a_value_error() -> None:
    with pytest.raises(ValueError, match="invalid OTLP payload"):
        export_request_from_resource_spans([{"scopeSpans": "not-a-list"}])


def test_a_non_string_output_attribute_is_skipped_rather_than_coerced() -> None:
    span: dict[str, Any] = {
        "traceId": _TRACE_ID,
        "spanId": "a" * 16,
        "name": "root",
        "endTimeUnixNano": "9",
        "attributes": [{"key": "output.value", "value": {"intValue": "7"}}],
    }

    assert final_output_text(export_request_from_resource_spans([{"scopeSpans": [{"spans": [span]}]}])) is None


def test_the_root_of_each_trace_is_considered_when_a_file_holds_several() -> None:
    first = _span("a" * 16, end=1)
    second = _span("b" * 16, end=2, **{"output.value": "second root"})

    assert _answer(first, second) == "second root"


def test_spans_with_equal_end_times_still_produce_an_answer() -> None:
    answer = _answer(
        _span("a" * 16, end=5),
        _span("b" * 16, end=5, parent="a" * 16, **{"output.value": "tied"}),
    )

    assert answer == "tied"


def test_a_deeply_nested_message_payload_does_not_escape_as_a_recursion_error() -> None:
    payload = "[" * 20000 + "]" * 20000

    assert _answer(_span("a" * 16, end=5, **{"gen_ai.output.messages": payload})) == payload


def test_deeply_nested_trace_text_surfaces_as_a_value_error() -> None:
    # RecursionError is not a ValueError, so leaking it would escape every caller's guard
    # and abort trial adaptation instead of falling back to the ATIF trace.
    with pytest.raises(ValueError, match="nested too deeply"):
        resource_spans_from_text("[" * 20000 + "]" * 20000)


def test_span_text_strings_reaches_every_nesting_the_attribute_schema_allows() -> None:
    resource_spans = [
        {
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "attributes": [
                                {"key": "plain", "value": {"stringValue": "on-span"}},
                                {"key": "skipped", "value": {"intValue": "5"}},
                                {"key": "arr", "value": {"arrayValue": {"values": [{"stringValue": "in-array"}]}}},
                                {
                                    "key": "kv",
                                    "value": {
                                        "kvlistValue": {
                                            "values": [
                                                {
                                                    "key": "nested",
                                                    "value": {
                                                        "arrayValue": {"values": [{"stringValue": "in-kvlist-array"}]}
                                                    },
                                                }
                                            ]
                                        }
                                    },
                                },
                            ],
                            "events": [
                                {"name": "e", "attributes": [{"key": "ek", "value": {"stringValue": "on-event"}}]}
                            ],
                        }
                    ]
                }
            ]
        }
    ]

    assert sorted(span_text_strings(resource_spans)) == [
        "in-array",
        "in-kvlist-array",
        "on-event",
        "on-span",
    ]


def test_span_text_strings_tolerates_malformed_containers() -> None:
    assert list(span_text_strings([{"scopeSpans": "not-a-list"}])) == []
    assert list(span_text_strings([{"scopeSpans": [{"spans": [{"attributes": "nope"}]}]}])) == []


_HEX_TRACE_ID = "0123456789abcdef0123456789abcdef"
_HEX_SPAN_ID = "0102030405060708"


def _parsed(*spans: dict[str, Any]):
    return export_request_from_resource_spans([{"scopeSpans": [{"spans": list(spans)}]}])


def test_otlp_json_hex_ids_survive_the_protobuf_parse() -> None:
    # OTLP/JSON writes ids as hex, departing from the protobuf JSON mapping ParseDict
    # implements; read as base64 a 16-character span id becomes twelve unrelated bytes.
    span = _parsed({"traceId": _HEX_TRACE_ID, "spanId": _HEX_SPAN_ID, "name": "root"})

    parsed = span.resource_spans[0].scope_spans[0].spans[0]
    assert parsed.trace_id.hex() == _HEX_TRACE_ID
    assert parsed.span_id.hex() == _HEX_SPAN_ID


def test_parent_and_link_ids_are_decoded_the_same_way() -> None:
    child = {
        "traceId": _HEX_TRACE_ID,
        "spanId": "aabbccddeeff0011",
        "parentSpanId": _HEX_SPAN_ID,
        "name": "child",
        "links": [{"traceId": _HEX_TRACE_ID, "spanId": _HEX_SPAN_ID}],
    }

    parsed = _parsed(child).resource_spans[0].scope_spans[0].spans[0]

    assert parsed.parent_span_id.hex() == _HEX_SPAN_ID
    assert parsed.links[0].span_id.hex() == _HEX_SPAN_ID


def test_a_base64_id_is_left_alone() -> None:
    # Only strings the right length for hex are converted, so a producer already using the
    # protobuf encoding is not corrupted.
    parsed = _parsed({"traceId": _HEX_TRACE_ID, "spanId": "AQIDBAUGBwg=", "name": "root"})

    assert parsed.resource_spans[0].scope_spans[0].spans[0].span_id.hex() == _HEX_SPAN_ID


def test_the_callers_resource_spans_are_not_mutated() -> None:
    resource_spans = [{"scopeSpans": [{"spans": [{"traceId": _HEX_TRACE_ID, "spanId": _HEX_SPAN_ID, "name": "root"}]}]}]

    export_request_from_resource_spans(resource_spans)

    assert resource_spans[0]["scopeSpans"][0]["spans"][0]["spanId"] == _HEX_SPAN_ID


def _nested_attribute_payload(depth: int) -> str:
    value = '{"arrayValue":{"values":[' * depth + '{"stringValue":"leaf"}' + "]}}" * depth
    return (
        '{"resourceSpans":[{"scopeSpans":[{"spans":[{"traceId":"%s","spanId":"%s","name":"s",'
        '"attributes":[{"key":"k","value":%s}]}]}]}]}' % (_HEX_TRACE_ID, _HEX_SPAN_ID, value)
    )


def test_a_deeply_nested_attribute_fails_conversion_as_a_value_error() -> None:
    # json.loads accepts this depth, so the decode-time guard does not fire; the conversion
    # recurses and must not leak RecursionError past a caller guarding on ValueError.
    resource_spans = resource_spans_from_text(_nested_attribute_payload(400))

    with pytest.raises(ValueError, match="nested too deeply"):
        export_request_from_resource_spans(resource_spans)


@pytest.mark.parametrize("depth", [400, 2000])
def test_span_text_strings_walks_any_depth(depth: int) -> None:
    resource_spans = resource_spans_from_text(_nested_attribute_payload(depth))

    assert list(span_text_strings(resource_spans)) == ["leaf"]


@pytest.mark.parametrize("kind", ["TOOL", "EVALUATOR", "RETRIEVER", "GUARDRAIL"])
def test_a_non_answer_span_is_never_the_answer(kind: str) -> None:
    # These record their output under the same `output.value` key an answer uses, so scoring
    # one as the model's answer would be silent rather than an error.
    answer = _answer(
        _span("a" * 16, end=1),
        _span("b" * 16, end=9, parent="a" * 16, kind=kind, **{"output.value": "NOT THE ANSWER"}),
    )

    assert answer is None


def test_a_non_answer_root_is_excluded_too() -> None:
    assert _answer(_span("a" * 16, end=5, kind="TOOL", **{"output.value": "tool only"})) is None


def test_a_span_declaring_no_kind_is_not_eligible() -> None:
    span = {
        "traceId": _TRACE_ID,
        "spanId": "a" * 16,
        "name": "no-kind",
        "endTimeUnixNano": "5",
        "attributes": [{"key": "output.value", "value": {"stringValue": "unattributed"}}],
    }

    assert _answer(span) is None


def test_span_kind_is_matched_case_insensitively() -> None:
    assert _answer(_span("a" * 16, end=5, kind="agent", **{"output.value": "answer"})) == "answer"
