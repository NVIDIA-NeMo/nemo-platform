# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime
from pathlib import Path

import pytest
from nemo_insights_plugin.contracts.profile import ProfileError
from nemo_insights_plugin.contracts.workflow_context import (
    WorkflowContext,
    load_workflow_context,
    resolve_context_base_url,
    write_workflow_context,
)


def _context() -> WorkflowContext:
    return WorkflowContext(
        agent="airline",
        workspace="airline-traces",
        base_url="http://platform.test",
        trace_source="state-v9",
        trace_since=datetime(2026, 7, 9, tzinfo=UTC),
    )


def test_workflow_context_round_trips(tmp_path: Path) -> None:
    path = write_workflow_context(tmp_path, _context())

    assert path == tmp_path / ".nemo-optimizer" / "context.yaml"
    assert load_workflow_context(tmp_path, agent="airline") == _context()


def test_workflow_context_rejects_another_agent(tmp_path: Path) -> None:
    write_workflow_context(tmp_path, _context())

    with pytest.raises(ProfileError, match="belongs to agent 'airline'"):
        load_workflow_context(tmp_path, agent="hotel")


def test_context_base_url_precedence() -> None:
    context = _context()

    assert (
        resolve_context_base_url(
            "http://flag.test",
            context,
            env={"NMP_BASE_URL": "http://shell.test"},
        )
        == "http://flag.test"
    )
    assert (
        resolve_context_base_url(
            None,
            context,
            env={"NMP_BASE_URL": "http://shell.test"},
        )
        == "http://shell.test"
    )
    assert resolve_context_base_url(None, context, env={}) == "http://platform.test"
