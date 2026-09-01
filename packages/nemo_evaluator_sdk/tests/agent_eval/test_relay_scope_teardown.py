# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression guard on the pinned ``nemo-relay`` wheel: NVBug 6562846.

Relay's LangChain callback handler used to pop chain scopes in callback order. LangGraph
schedules sibling runs concurrently, so the out-of-order pop was rejected and swallowed,
the child scope was stranded on the stack, and the enclosing scope's teardown then raised.
Fabric's DeepAgents adapter reported that as the agent's own failure, failing Evaluator
trials whose work had completed.
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

    with caplog.at_level(logging.ERROR, logger=callbacks.__name__):
        with nemo_relay.use_scope_stack(nemo_relay.create_scope_stack()):
            with nemo_relay.scope.scope("deepagents-request", nemo_relay.ScopeType.Agent):
                handler.on_chain_start({"name": "chain-A"}, {"in": "a"}, run_id=chain_a)
                handler.on_chain_start({"name": "chain-B"}, {"in": "b"}, run_id=chain_b)
                assert nemo_relay.scope.get_handle().name == "chain-B"

                handler.on_chain_end({"out": "a"}, run_id=chain_a)
                handler.on_chain_end({"out": "b"}, run_id=chain_b)

                assert nemo_relay.scope.get_handle().name == "deepagents-request"

    assert [record.message for record in caplog.records if record.name == callbacks.__name__] == []
