# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from coding_agents.claude_code.result import find_result_in_jsonl, to_result_event
from coding_agents.events import ResultEvent


# Happy-path translation: a stream-json result line with subtype="success"
# and is_error=false becomes a ResultEvent(success=True) with cost, duration,
# stop_reason, and final text populated from the raw fields.
def test_to_result_event_success(tmp_path):
    ev = to_result_event(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "duration_ms": 1234,
            "num_turns": 1,
            "result": "done",
            "stop_reason": "end_turn",
            "total_cost_usd": 0.01,
        },
        session_id="run-abc",
        artifact_dir=tmp_path,
    )
    assert isinstance(ev, ResultEvent)
    assert ev.session_id == "run-abc"
    assert ev.artifact_dir == tmp_path
    assert ev.success is True
    assert ev.text == "done"
    assert ev.cost_usd == 0.01
    assert ev.duration_ms == 1234
    assert ev.stop_reason == "end_turn"


# Gotcha: Claude Code can emit subtype="success" *and* is_error=true on the
# same line. The `success` flag must reflect both — a "successful" result
# that's actually an error should surface as success=False.
def test_to_result_event_is_error_overrides_subtype(tmp_path):
    ev = to_result_event(
        {
            "type": "result",
            "subtype": "success",
            "is_error": True,
            "stop_reason": "error",
        },
        session_id="run-xyz",
        artifact_dir=tmp_path,
    )
    assert ev.success is False


# Scanner finds the result line even when it's preceded by other event
# types and non-JSON noise. Mirrors what real stream-json files look like:
# system/init, assistant chunks, then a single result line at the end.
def test_find_result_in_jsonl_walks_to_result(tmp_path):
    jsonl = tmp_path / "turn_0000.jsonl"
    jsonl.write_text(
        "garbage non-json line\n"
        '{"type":"system","subtype":"init","session_id":"abc"}\n'
        '{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"hi"}]}}\n'
        '{"type":"result","subtype":"success","is_error":false,"result":"ok","total_cost_usd":0.05}\n'
    )
    raw = find_result_in_jsonl(jsonl)
    assert raw is not None
    assert raw["type"] == "result"
    assert raw["result"] == "ok"


# Negative case: a JSONL file with no result line returns None (caller's
# cue to raise AgentRunError because the process died without finishing).
def test_find_result_in_jsonl_missing_result_returns_none(tmp_path):
    jsonl = tmp_path / "turn_0000.jsonl"
    jsonl.write_text(
        '{"type":"system","subtype":"init"}\n{"type":"assistant","message":{"role":"assistant","content":[]}}\n'
    )
    assert find_result_in_jsonl(jsonl) is None


# Negative case: missing file (process never even wrote to stdout) returns
# None rather than raising. Same caller path as "no result line".
def test_find_result_in_jsonl_missing_file_returns_none(tmp_path):
    assert find_result_in_jsonl(tmp_path / "does-not-exist.jsonl") is None
