# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression guard on the pinned ``nemo-relay`` wheel: NVBug 6562846.

A Relay scope stack closes strictly LIFO, but LangGraph schedules sibling chain runs
concurrently, so a run can end while scopes opened after it are still open. Relay's
LangChain callback handler used to pop in callback order: the out-of-order pop was
rejected and swallowed, the child scope was stranded live on the stack, and the
*enclosing* scope's teardown then raised. Fabric's DeepAgents adapter reported that
teardown fault as the agent's own failure, so Evaluator trials that had completed their
work — model calls, tool calls, a final response — came back failed.

The guard runs in the ordinary unit lane: ``nemo-agents-plugin`` is in the root
``enabled-plugins`` group, so a default workspace sync installs Relay's LangChain
integration and its ``langchain`` dependency. The skip is for the package-scoped lanes
that install neither.
"""

from __future__ import annotations

import logging
import uuid

import pytest

nemo_relay = pytest.importorskip("nemo_relay")
callbacks = pytest.importorskip("nemo_relay.integrations.langchain.callbacks")


def test_overlapping_chain_runs_leave_the_enclosing_scope_closable(caplog: pytest.LogCaptureFixture) -> None:
    """Closing chain A while chain B is still open must not corrupt the stack."""
    handler = callbacks.NemoRelayCallbackHandler()
    chain_a, chain_b = uuid.uuid4(), uuid.uuid4()

    # Own stack: a regression strands a scope, which on the ambient stack leaks into the next test.
    with caplog.at_level(logging.ERROR, logger=callbacks.__name__):
        with nemo_relay.use_scope_stack(nemo_relay.create_scope_stack()):
            with nemo_relay.scope.scope("deepagents-request", nemo_relay.ScopeType.Agent):
                handler.on_chain_start({"name": "chain-A"}, {"in": "a"}, run_id=chain_a)
                handler.on_chain_start({"name": "chain-B"}, {"in": "b"}, run_id=chain_b)
                # Both children are really open, so the closes below overlap for real.
                assert nemo_relay.scope.get_handle().name == "chain-B"

                # A ends from under B: the out-of-LIFO close.
                handler.on_chain_end({"out": "a"}, run_id=chain_a)
                handler.on_chain_end({"out": "b"}, run_id=chain_b)

                # Against a stranded child this is "chain-A", and leaving the block raises.
                assert nemo_relay.scope.get_handle().name == "deepagents-request"

    # A rejected pop is logged and swallowed, leaving the run telemetry-broken but silent.
    assert [record.message for record in caplog.records if record.name == callbacks.__name__] == []
