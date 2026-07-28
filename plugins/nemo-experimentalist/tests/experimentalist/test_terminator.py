# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the Terminator step.

These guard the behavior-preserving extraction of the termination logic
(``_has_converged`` + ``qualitative_stop_check`` + ``max_rounds``) out of the
loop and into :mod:`terminator`. Every Terminator is constructed with an injected
``FakeLLMClient`` so the tests need no ``EXPERIMENTALIST_API_*`` env vars and make no
network calls.
"""

import json
from dataclasses import dataclass, field
from types import SimpleNamespace

from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.experimentalist.components.terminator import (
    TerminationDecision,
    Terminator,
)
from nooa.unifiedllm import FakeLLMClient, LLMResponse, ToolCall


@dataclass
class _FakeNode:
    """Stand-in for EvolutionNode exposing only what _has_converged reads."""

    label: str
    round: int
    val_reward: dict[str, float] = field(default_factory=dict)


def _tree(*nodes: _FakeNode) -> SimpleNamespace:
    """Build a stand-in EvolutionTree: an object with a ``.nodes`` dict."""
    return SimpleNamespace(nodes={n.label: n for n in nodes})


def _exec_response(code: str) -> LLMResponse:
    """A scripted LLM turn that drives CodeAct's ``execute_python`` tool with ``code``."""
    return LLMResponse(
        raw_response=None,
        content="",
        finish_reason="tool_calls",
        assistant_message={"role": "assistant", "content": ""},
        tool_calls=[ToolCall(id="call_exec", name="execute_python", arguments=json.dumps({"code": code}))],
    )


def _terminator(*, stop_verdict: bool | None = None) -> Terminator:
    """Build a Terminator with an injected fake LLM.

    When ``stop_verdict`` is None the fake makes no scripted response (used by tests
    that never reach the qualitative check). Otherwise the qualitative_stop_check
    strategy resolves to that boolean via a scripted ``return_result``.
    """
    if stop_verdict is None:
        return Terminator(llm=FakeLLMClient())
    fake = FakeLLMClient(scripted_responses=[_exec_response(f"return_result(result={stop_verdict})")])
    return Terminator(llm=fake)


# ---------------------------------------------------------------------------
# assess_round_budget
# ---------------------------------------------------------------------------


def test_assess_round_budget_stops_at_max_rounds() -> None:
    term = _terminator()
    config = EvolutionaryOptimizerConfig(max_rounds=3)

    assert term.assess_round_budget(round_num=2, config=config) == TerminationDecision(stop=False)

    at_limit = term.assess_round_budget(round_num=3, config=config)
    assert at_limit.stop is True
    assert "max_rounds" in at_limit.reason

    assert term.assess_round_budget(round_num=4, config=config).stop is True


# ---------------------------------------------------------------------------
# run() — unified entry point (budget first, then convergence)
# ---------------------------------------------------------------------------


async def test_run_stops_on_budget() -> None:
    term = _terminator()
    config = EvolutionaryOptimizerConfig(max_rounds=2)
    decision = await term.run(
        round_num=2,
        evolution_tree=_tree(),
        prior_analysis=None,
        config=config,
    )
    assert decision.stop is True
    assert "max_rounds" in decision.reason


async def test_run_stops_on_convergence_when_budget_not_hit() -> None:
    term = _terminator()
    # Budget not exhausted (round 2 < max_rounds 15), but the front has stagnated.
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.9}),
        _FakeNode("a1", 1, {"score": 0.5}),
        _FakeNode("a2", 2, {"score": 0.6}),
    )
    decision = await term.run(
        round_num=2,
        evolution_tree=tree,
        prior_analysis="prior analysis",
        config=EvolutionaryOptimizerConfig(max_rounds=15, min_rounds_before_stopping=2),
    )
    assert decision.stop is True
    assert "converged" in decision.reason


async def test_run_continues_when_neither_triggers() -> None:
    term = _terminator()
    decision = await term.run(
        round_num=0,
        evolution_tree=_tree(),
        prior_analysis=None,  # round 0: no convergence check
        config=EvolutionaryOptimizerConfig(max_rounds=15),
    )
    assert decision == TerminationDecision(stop=False)


# ---------------------------------------------------------------------------
# assess_convergence gating (no LLM, no deterministic work)
# ---------------------------------------------------------------------------


async def test_assess_convergence_no_prior_analysis_does_not_stop() -> None:
    term = _terminator()
    config = EvolutionaryOptimizerConfig()
    decision = await term.assess_convergence(
        evolution_tree=_tree(),
        prior_analysis=None,
        config=config,
    )
    assert decision == TerminationDecision(stop=False)


async def test_assess_convergence_disabled_does_not_stop() -> None:
    term = _terminator()
    config = EvolutionaryOptimizerConfig(disable_convergence_check=True)
    # A tree that WOULD converge — proves the disable flag short-circuits first.
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.9}),
        _FakeNode("a1", 1, {"score": 0.5}),
        _FakeNode("a2", 2, {"score": 0.6}),
    )
    decision = await term.assess_convergence(
        evolution_tree=tree,
        prior_analysis="some analysis",
        config=config,
    )
    assert decision == TerminationDecision(stop=False)


# ---------------------------------------------------------------------------
# _has_converged deterministic paths
# ---------------------------------------------------------------------------


async def test_has_converged_false_when_too_few_rounds() -> None:
    term = _terminator()
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.5}),
        _FakeNode("a1", 1, {"score": 0.6}),
    )
    # Only 2 distinct scored rounds < min_rounds_before_stopping=3 -> False, no LLM.
    assert (
        await term._has_converged(
            evolution_tree=tree,
            prior_analysis="ignored",
            min_rounds_before_stopping=3,
        )
        is False
    )


async def test_has_converged_ignores_unscored_nodes() -> None:
    term = _terminator()
    # Two scored rounds + an unscored ({}) node. The unscored node must NOT count toward the
    # round set (val_reward is {} for unscored, so a truthy filter excludes it); with only two
    # scored rounds < min_rounds_before_stopping=3 the check returns False.
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.5}),
        _FakeNode("a1", 1, {"score": 0.6}),
        _FakeNode("a2", 2, {}),  # unscored — must be ignored
    )
    assert (
        await term._has_converged(
            evolution_tree=tree,
            prior_analysis="ignored",
            min_rounds_before_stopping=3,
        )
        is False
    )


async def test_has_converged_true_when_front_stagnates() -> None:
    term = _terminator()
    # Best candidate is the round-0 baseline; later rounds never beat it, so the
    # full Pareto front (a0) is a subset of the old front (a0) -> converged.
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.9}),
        _FakeNode("a1", 1, {"score": 0.5}),
        _FakeNode("a2", 2, {"score": 0.6}),
    )
    assert (
        await term._has_converged(
            evolution_tree=tree,
            prior_analysis="ignored",
            min_rounds_before_stopping=2,
        )
        is True
    )


# ---------------------------------------------------------------------------
# Qualitative fallback (deterministic check inconclusive -> LLM decides)
# ---------------------------------------------------------------------------


async def test_qualitative_fallback_true() -> None:
    term = _terminator(stop_verdict=True)
    # Newest round (a2=0.7) is the unique front, NOT in the old front -> not a
    # deterministic stop, so the qualitative check is consulted.
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.5}),
        _FakeNode("a1", 1, {"score": 0.6}),
        _FakeNode("a2", 2, {"score": 0.7}),
    )
    assert (
        await term._has_converged(
            evolution_tree=tree,
            prior_analysis="plateaued: same root cause every round",
            min_rounds_before_stopping=2,
        )
        is True
    )


async def test_qualitative_fallback_false_propagates_through_assess_convergence() -> None:
    term = _terminator(stop_verdict=False)
    tree = _tree(
        _FakeNode("a0", 0, {"score": 0.5}),
        _FakeNode("a1", 1, {"score": 0.6}),
        _FakeNode("a2", 2, {"score": 0.7}),
    )
    decision = await term.assess_convergence(
        evolution_tree=tree,
        prior_analysis="still improving",
        config=EvolutionaryOptimizerConfig(min_rounds_before_stopping=2),
    )
    assert decision == TerminationDecision(stop=False)


# Winner publishing moved off the Terminator: the loop gates on config.storage.publish_winner and
# calls backend.publish_candidate directly. Its behavior is covered in test_experimentalist_backend.
