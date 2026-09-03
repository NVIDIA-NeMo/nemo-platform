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


def test_build_ingest_payload_raises_when_schema_version_is_absent(tmp_path):
    ref = _ref(tmp_path, _trajectory(schema_version=None))
    with pytest.raises(ValueError, match="no schema_version"):
        build_ingest_payload(ref, evaluation_name="exp-1", task_id="case-a", agent_attrs={})


@pytest.mark.parametrize(
    "agent",
    [
        pytest.param({}, id="empty"),
        pytest.param({"name": "Codeact"}, id="no-version"),
        pytest.param({"version": "1.0"}, id="no-name"),
    ],
)
def test_build_ingest_payload_raises_when_agent_identity_is_absent(tmp_path, agent):
    # Without these the cast would claim a shape the payload does not have.
    ref = _ref(tmp_path, _trajectory(agent=agent))
    with pytest.raises(ValueError, match="no agent name and version"):
        build_ingest_payload(ref, evaluation_name="exp-1", task_id="case-a", agent_attrs={})


def test_build_ingest_payload_names_the_agent_type_when_it_is_not_an_object(tmp_path):
    # "no name and version" would send a producer looking for missing fields rather than
    # a wrong type.
    ref = _ref(tmp_path, _trajectory(agent="Codeact"))
    with pytest.raises(ValueError, match="agent is not an object"):
        build_ingest_payload(ref, evaluation_name="exp-1", task_id="case-a", agent_attrs={})


def test_build_ingest_payload_accepts_blank_agent_identity(tmp_path):
    # Intake types agent name and version as plain str, so blank is valid; the guard
    # checks presence, not content, and must not be stricter than the server.
    ref = _ref(tmp_path, _trajectory(agent={"name": "", "version": ""}))

    payload = build_ingest_payload(ref, evaluation_name="exp-1", task_id="case-a", agent_attrs={})

    assert payload["agent"] == {"name": "", "version": ""}


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
