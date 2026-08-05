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
from nemo_experimentalist_plugin.experimentalist.registry import (
    Component,
    get_component,
    load_plugins,
    registered,
    resolve,
)
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

    Two hazards, both of which have bitten:

    Restore the mapping's *contents*, never the object. Entry-point discovery writes into
    whichever dict is bound at the time and runs once per process, so replacing the object
    sends the real components into a copy that is then discarded.

    And discover *before* snapshotting. Taking the snapshot first captures an empty
    registry, and the teardown then restores that emptiness over the real components.
    """
    load_plugins()
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


def test_an_installed_out_of_tree_package_is_discovered() -> None:
    """The developer journey of §1, checked rather than described.

    `examples/acme-strategies` is a separate package with its own pyproject and one entry
    point. When it is installed, its strategy resolves by name here with no change to this
    repository — which is the only evidence that both discovery levels work for someone
    who is not us.

    Skipped when it is not installed, so the suite does not require it; CI installs it.
    """
    pytest.importorskip("acme_strategies", reason="out-of-tree example package is not installed")

    resolved = resolve("strategy", "random-search")

    assert resolved.__module__.startswith("acme_strategies"), "resolved to something in this repo"
    assert issubclass(resolved, Strategy)
    assert "random-search" in registered("strategy")


@pytest.mark.asyncio
async def test_the_round_budget_bounds_the_loop_without_a_terminator() -> None:
    """`max_rounds` must hold even when no terminator is selected.

    The loop used to be `while True`, with the only bound living inside the default
    terminator's budget check. Selecting a different terminator — or none — therefore
    removed the budget too, and the run kept proposing until something else failed. A
    component's opinion must not be the only thing between a config and an unbounded run.
    """
    import inspect

    from nemo_experimentalist_plugin.experimentalist.strategies import evolutionary

    source = inspect.getsource(evolutionary.EvolutionaryStrategy._run)

    assert "while True" not in source, "the optimization loop must bound itself"
    assert "while round_num < config.max_rounds" in source


@pytest.mark.asyncio
async def test_a_swapped_component_can_actually_be_built_and_called(tmp_path, isolated_registry: None) -> None:
    """Resolution is not the bar; construction and use are.

    Every default resolved by name and then failed on its constructor, because
    `ctx.component` did not supply the run-scoped arguments a component cannot know for
    itself. The earlier version of this file asserted `resolve(...) is not None` and
    passed throughout — which is how two half-connected seams reached a review.
    """
    from doubles import FakeBackend, make_context

    ctx = make_context(root=tmp_path, backend=FakeBackend())

    for role, key in ROLES.items():
        if role == "strategy":
            continue  # built by the runner, not by a strategy through the context
        name = getattr(EvolutionaryOptimizerConfig(), key)
        built = ctx.component(role, name)
        assert built is not None, f"{role}={name!r} resolved but could not be constructed"


@pytest.mark.asyncio
async def test_a_swapped_builder_runs_through_the_context(tmp_path, isolated_registry: None) -> None:
    """The narrowest end-to-end check of the seam: config names it, the context builds
    it, and it produces a Candidate through the same verbs the built-in Coder uses."""
    from doubles import FakeBackend, make_context

    class StubBuilder(Builder):
        name = "acme-noop"
        accepts: ClassVar[frozenset[str]] = frozenset({"code-change"})

        def __init__(self, **kwargs: Any) -> None:
            pass

        async def build(self, ctx: Any, proposal: Proposal, *, generation: int = 0) -> Candidate:
            fork = await ctx.fork(proposal)
            (fork.workdir / "changed.py").write_text("# built by an out-of-tree builder\n")
            return await ctx.commit_candidate(proposal=proposal, artifact=fork.workdir, generation=generation)

    ctx = make_context(root=tmp_path, backend=FakeBackend())
    baseline = await ctx.component("builder", "import").build(
        ctx, Proposal(ancestor=None, description="baseline", kind="import", payload={}), generation=0
    )
    proposal = Proposal(ancestor=baseline.id, description="a change", kind="code-change", payload={})

    candidate = await ctx.component("builder", "acme-noop").build(ctx, proposal, generation=1)

    assert candidate.ancestor == baseline.id
    assert (ctx.candidate_dir(candidate) / "changed.py").exists()
