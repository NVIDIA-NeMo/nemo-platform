# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""M1's acceptance bar: every seam is swappable from config, with no code change.

The milestone claims the core is done. The test of that claim is that a new
optimization paradigm — HPO next — needs no edit to the strategy or to any existing
component. If a role cannot be named in config and resolved, that claim is false, and
this file says so rather than leaving it to be discovered when HPO is written.

Each replacement below is deliberately a stub. What is under test is resolution: that
the role exists, that config names it, and that the registry hands back the class the
config asked for.
"""

from collections.abc import Iterator
from typing import Any, ClassVar

import pytest
from nemo_experimentalist_plugin.config import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.entities import Candidate, Proposal
from nemo_experimentalist_plugin.experimentalist.registry import Component, get_component, registered, resolve
from nemo_experimentalist_plugin.experimentalist.roles import (
    Analyzer,
    Builder,
    Evaluation,
    Proposer,
    Selector,
    Strategy,
    Terminator,
    TrajectoryScorer,
)

#: Every role the evolutionary strategy delegates to, and the config key naming it.
ROLES = {
    "strategy": "strategy",
    "builder": "builder",
    "evaluation": "evaluation",
    "proposer": "proposer",
    "selector": "selector",
    "terminator": "terminator",
    "root-cause-analyzer": "analyzer",
    "trajectory-scorer": "trajectory_scorer",
}


@pytest.fixture
def isolated_registry() -> Iterator[None]:
    """Register stand-ins without leaking them into other tests.

    Restores the mapping's *contents* rather than swapping the object: entry-point
    discovery writes into whichever dict is bound at the time, and it only runs once per
    process, so a test that replaced the object would send the real components into a copy
    that is then thrown away — leaving every later lookup empty.
    """
    before = dict(Component._registry)
    yield
    Component._registry.clear()
    Component._registry.update(before)


def test_the_defaults_name_a_component_that_exists(isolated_registry: None) -> None:
    """A default that does not resolve is a run that dies after the user waits for it."""
    config = EvolutionaryOptimizerConfig()
    for role, key in ROLES.items():
        name = getattr(config, key)
        assert name is not None, f"{key} has no default"
        assert resolve(role, name) is not None, f"default {key}={name!r} does not resolve"


def test_every_role_can_be_swapped_for_one_this_repo_does_not_know(isolated_registry: None) -> None:
    """The whole milestone in one assertion.

    Each stand-in registers the way a `pip install`ed package's would, and config names
    it. Nothing in the strategy or in any existing component changes.
    """

    class Swapped:
        """Marks a class as the replacement, so resolution can be told from a default."""

    class SwappedStrategy(Swapped, Strategy):
        name = "acme-bandit"
        supports_resume: ClassVar[bool] = False

    class SwappedBuilder(Swapped, Builder):
        name = "acme-overlay"
        accepts: ClassVar[frozenset[str]] = frozenset({"parameters"})

    class SwappedEvaluation(Swapped, Evaluation):
        name = "acme-scorer"

    class SwappedProposer(Swapped, Proposer):
        name = "acme-hpo"
        produces: ClassVar[frozenset[str]] = frozenset({"parameters"})

    class SwappedSelector(Swapped, Selector):
        name = "acme-crowding"

    class SwappedTerminator(Swapped, Terminator):
        name = "acme-budget"

    class SwappedAnalyzer(Swapped, Analyzer):
        name = "acme-blind"

    class SwappedScorer(Swapped, TrajectoryScorer):
        name = "acme-steps"

    config = EvolutionaryOptimizerConfig(
        strategy="acme-bandit",
        builder="acme-overlay",
        evaluation="acme-scorer",
        proposer="acme-hpo",
        selector="acme-crowding",
        terminator="acme-budget",
        analyzer="acme-blind",
        trajectory_scorer="acme-steps",
    )

    for role, key in ROLES.items():
        resolved = resolve(role, getattr(config, key))
        assert issubclass(resolved, Swapped), f"{role} resolved to {resolved.__name__}, not the configured one"


def test_a_role_can_be_turned_off_by_naming_no_component() -> None:
    """Turning a step off is the degenerate case of choosing a different implementation.

    Only the genuinely optional steps accept it: a run with no proposer or no builder
    would have nothing to do.
    """
    config = EvolutionaryOptimizerConfig(analyzer=None, terminator=None, trajectory_scorer=None)

    assert (config.analyzer, config.terminator, config.trajectory_scorer) == (None, None, None)
    assert config.proposer and config.builder and config.selector and config.strategy


def test_resolution_constructs_with_what_the_caller_passes(isolated_registry: None) -> None:
    """A replacement is built by the strategy that resolves it, on that strategy's terms."""
    seen: dict[str, Any] = {}

    class RecordingBuilder(Builder):
        name = "acme-recording"
        accepts: ClassVar[frozenset[str]] = frozenset({"code-change"})

        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

        async def build(self, ctx: Any, proposal: Proposal, *, generation: int) -> Candidate:
            raise NotImplementedError

    get_component("builder", "acme-recording", workspace="/tmp", config=None, models=None)

    assert seen == {"workspace": "/tmp", "config": None, "models": None}


def test_the_installed_defaults_are_discoverable_without_importing_them() -> None:
    """What `nemo agents experimentalist components` reads, and what a plugin author
    checks their package against."""
    for role in ROLES:
        assert registered(role), f"no component registered for {role}"
