# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""How the optional artifacts are assembled into the analyst's instructions."""

import pytest
from nemo_insights_plugin.analyst.agent import (
    AGENT_SPEC_HEADER,
    SEEDED_FINDINGS_HEADER,
    build_analyst_agent,
)


@pytest.fixture(autouse=True)
def inference_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """``build_analyst_agent`` constructs a provider, which reads this key."""
    monkeypatch.setenv("INFERENCE_API_KEY", "test-key")


def _instructions(agent_spec: str | None = None, seeded_findings: str | None = None) -> str:
    """The agent's assembled system prompt, which Pydantic AI holds as a sequence."""
    built = build_analyst_agent(
        agent="flight-planner",
        agent_spec=agent_spec,
        seeded_findings=seeded_findings,
    )
    raw = built._instructions
    if isinstance(raw, str):
        return raw
    return "".join(str(part) for part in raw or [])


def test_seeded_findings_are_appended_under_their_own_header() -> None:
    text = _instructions(seeded_findings="Sessions time out at 60s.")

    assert SEEDED_FINDINGS_HEADER.strip() in text
    assert "Sessions time out at 60s." in text


def test_seeded_findings_stay_separate_from_the_spec() -> None:
    """The digest must not land under the spec header, where it would read as contract."""
    text = _instructions(
        agent_spec="# Contract\nPlan flights.",
        seeded_findings="# Digest\nPlanner loops on retries.",
    )

    spec_at = text.index("Plan flights.")
    findings_header_at = text.index(SEEDED_FINDINGS_HEADER.strip())
    assert text.index(AGENT_SPEC_HEADER.strip()) < spec_at < findings_header_at
    assert findings_header_at < text.index("Planner loops on retries.")


@pytest.mark.parametrize("value", [None, "", "   \n  "])
def test_blank_seeded_findings_add_no_header(value: str | None) -> None:
    assert SEEDED_FINDINGS_HEADER.strip() not in _instructions(seeded_findings=value)
