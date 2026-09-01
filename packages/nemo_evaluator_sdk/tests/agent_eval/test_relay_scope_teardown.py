# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression guard on the pinned ``nemo-relay`` wheel: NVBug 6562846.

A Relay scope stack closes strictly LIFO, but LangGraph schedules sibling chain runs
concurrently, so a run can end while scopes opened after it are still open. Up to and
including ``nemo-relay`` 0.7.2 the LangChain callback handler popped in callback order:
the out-of-order pop was rejected and swallowed, the child scope was stranded live on the
stack, and the *enclosing* scope's teardown then raised ``RuntimeError: invalid argument:
scope handle is not at the top of the stack``. Fabric's DeepAgents adapter reported that
teardown fault as the agent's own failure, so Evaluator trials that had completed their
work — model calls, tool calls, a final response — came back failed.

0.7.3 defers a completed scope until it reaches the top of the stack, which is what this
asserts, against the real handler rather than a stand-in.

This runs in the ordinary unit lane: ``nemo-agents-plugin`` is in the root ``enabled-plugins``
group, so a default workspace sync installs Relay's LangChain integration and its ``langchain``
dependency. The skip is for the package-scoped lanes that install neither.
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

    # A stack of this test's own: a regression strands a scope, and on the ambient stack that
    # damage would travel to whatever runs next in this worker.
    with caplog.at_level(logging.ERROR, logger=callbacks.__name__):
        with nemo_relay.use_scope_stack(nemo_relay.create_scope_stack()):
            with nemo_relay.scope.scope("deepagents-request", nemo_relay.ScopeType.Agent):
                handler.on_chain_start({"name": "chain-A"}, {"in": "a"}, run_id=chain_a)
                handler.on_chain_start({"name": "chain-B"}, {"in": "b"}, run_id=chain_b)
                # Both children are really open, so the closes below are the overlapping
                # sequence and not a no-op the assertions would wave through.
                assert nemo_relay.scope.get_handle().name == "chain-B"

                # A ends first, from under B: the out-of-LIFO close that used to strand a scope.
                handler.on_chain_end({"out": "a"}, run_id=chain_a)
                handler.on_chain_end({"out": "b"}, run_id=chain_b)

                # On 0.7.2 the top here is the stranded "chain-A", and leaving this block raises.
                assert nemo_relay.scope.get_handle().name == "deepagents-request"

    # A rejected pop is logged and swallowed, so a run can be left telemetry-broken without
    # anything raising. That half of the defect is invisible to the assertions above.
    assert [record.message for record in caplog.records if record.name == callbacks.__name__] == []
