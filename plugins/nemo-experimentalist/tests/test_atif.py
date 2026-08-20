# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for the ATIF trajectory helpers.

Asserted through observable output — the session id string or the assembled
payload dict — never through private helpers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.entities import ResourceRef
from nemo_experimentalist_plugin.experimentalist.atif import build_ingest_payload, read_session_id

SESSION_ID = "d074dfb7-3691-443c-b137-720d75e40afa"

AGENT_ATTRS = {
    "gen_ai.agent.name": "nemo-experimentalist-tau3-nooa",
    "agent.version": "1.0.0",
    "gen_ai.request.model": "openai/openai/openai/gpt-5-mini",
}


def _trajectory(**overrides: object) -> dict:
    base: dict = {
        "schema_version": "ATIF-v1.7",
        "session_id": SESSION_ID,
        "agent": {"name": "Codeact", "version": "0.0.0"},
        "steps": [{"step_id": 1, "source": "user", "message": "hi"}],
    }
    base.update(overrides)
    return base


def _ref(tmp_path: Path, trajectory: dict) -> ResourceRef:
    path = tmp_path / f"trajectory-{SESSION_ID}.atif.json"
    path.write_text(json.dumps(trajectory), encoding="utf-8")
    return ResourceRef(uri=f"file://{path}", description="", metadata={})


# ---------------------------------------------------------------------------
# read_session_id
# ---------------------------------------------------------------------------


def test_read_session_id_returns_the_trajectory_session_id(tmp_path):
    assert read_session_id(_ref(tmp_path, _trajectory())) == SESSION_ID


def test_read_session_id_raises_when_absent(tmp_path):
    ref = _ref(tmp_path, _trajectory(session_id=None))
    with pytest.raises(ValueError, match="No session_id"):
        read_session_id(ref)


def test_read_session_id_raises_on_empty_string(tmp_path):
    ref = _ref(tmp_path, _trajectory(session_id=""))
    with pytest.raises(ValueError, match="No session_id"):
        read_session_id(ref)


# ---------------------------------------------------------------------------
# build_ingest_payload
# ---------------------------------------------------------------------------


def test_build_ingest_payload_stamps_evaluation_context(tmp_path):
    payload = build_ingest_payload(
        _ref(tmp_path, _trajectory()),
        evaluation_name="exp-1",
        task_id="tau3-airline/case-a",
        agent_attrs={},
    )
    assert payload["evaluation_context"] == {
        "evaluation_name": "exp-1",
        "test_case_name": "tau3-airline/case-a",
    }


def test_build_ingest_payload_preserves_producer_fields(tmp_path):
    payload = build_ingest_payload(
        _ref(tmp_path, _trajectory()),
        evaluation_name="exp-1",
        task_id="case-a",
        agent_attrs={},
    )
    assert payload["schema_version"] == "ATIF-v1.7"
    assert payload["session_id"] == SESSION_ID
    assert payload["steps"] == [{"step_id": 1, "source": "user", "message": "hi"}]


def test_build_ingest_payload_fills_only_blank_agent_fields(tmp_path):
    # Producer set name and version; model_name is absent.
    payload = build_ingest_payload(
        _ref(tmp_path, _trajectory()),
        evaluation_name="exp-1",
        task_id="case-a",
        agent_attrs=AGENT_ATTRS,
    )
    assert payload["agent"]["name"] == "Codeact"  # not overwritten
    assert payload["agent"]["version"] == "0.0.0"  # not overwritten
    assert payload["agent"]["model_name"] == "openai/openai/openai/gpt-5-mini"  # filled


def test_build_ingest_payload_fills_missing_agent_block(tmp_path):
    trajectory = _trajectory()
    del trajectory["agent"]
    payload = build_ingest_payload(
        _ref(tmp_path, trajectory),
        evaluation_name="exp-1",
        task_id="case-a",
        agent_attrs=AGENT_ATTRS,
    )
    assert payload["agent"] == {
        "name": "nemo-experimentalist-tau3-nooa",
        "version": "1.0.0",
        "model_name": "openai/openai/openai/gpt-5-mini",
    }


def test_build_ingest_payload_does_not_inject_verifier_result(tmp_path):
    payload = build_ingest_payload(
        _ref(tmp_path, _trajectory()),
        evaluation_name="exp-1",
        task_id="case-a",
        agent_attrs=AGENT_ATTRS,
    )
    assert "verifier_result" not in payload.get("extra", {})
