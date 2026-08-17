# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The plugin mechanism: components are found by ``(role, name)``.

This is what a developer relies on when they ``pip install`` their own package beside
ours and select it by name, so the two behaviours that differ are pinned here: resolving
a name never falls back, and enumerating never lets one broken package take down a run
that does not use it.
"""

import types
from typing import ClassVar

import pytest
from nemo_experimentalist_plugin.experimentalist import registry as registry_module
from nemo_experimentalist_plugin.experimentalist.registry import (
    Component,
    get_component,
    load_plugins,
    registered,
    resolve,
)
from nemo_experimentalist_plugin.experimentalist.roles import Builder, Strategy


def test_our_own_components_are_discovered_through_the_entry_point_group() -> None:
    """No privileged built-ins: ours ship an entry point exactly like a third party's.

    If this breaks, the mechanism a plugin developer depends on is broken too — which is
    the point of registering ours the same way rather than importing them directly.
    """
    assert "evolutionary" in registered("strategy")
    assert "code-edit" in registered("builder")


def test_resolving_an_unknown_name_raises_and_says_what_is_known() -> None:
    """Never skip, never fall back. A run configured for a strategy that is not installed
    must not quietly run a different one and report a result for a question nobody asked."""
    with pytest.raises(LookupError) as excinfo:
        resolve("strategy", "not-installed")

    message = str(excinfo.value)
    assert "not-installed" in message
    assert "evolutionary" in message, "the error should list what is available"


def test_a_role_base_class_does_not_register_itself() -> None:
    """``Strategy`` and ``Builder`` declare a slot; they are not implementations of one."""
    assert ("strategy", "") not in Component._registry
    assert ("builder", "") not in Component._registry
    assert Strategy.name == ""
    assert Builder.name == ""


def test_two_different_classes_claiming_one_name_is_an_error() -> None:
    """Last-win is the wrong semantics for a named component that must exist."""
    with pytest.raises(RuntimeError, match="duplicate component builder.code-edit"):

        class Clashing(Builder):
            name = "code-edit"


def test_re_executing_a_component_module_is_not_a_duplicate() -> None:
    """A module reachable twice — reloaded, or importable by two paths — re-registers.

    Comparing by object identity reported a class as a duplicate of itself, with both
    sides of the message naming the same class.

    Built by hand rather than with ``importlib.reload`` on the real module: reloading
    rebinds every class in it, so the config tree's ``CodeEditBuilderConfig`` would stop being the
    same object as the freshly imported one and unrelated tests would fail.
    """
    from nemo_experimentalist_plugin.experimentalist.components.coder import CodeEditBuilder

    def _same_identity(namespace: dict[str, object]) -> None:
        namespace["name"] = "code-edit"
        namespace["__module__"] = CodeEditBuilder.__module__
        namespace["__qualname__"] = CodeEditBuilder.__qualname__

    try:
        stand_in = types.new_class("CodeEditBuilder", (Builder,), exec_body=_same_identity)  # must not raise

        # It really did re-register: the entry now points at the stand-in, not the real
        # CodeEditBuilder. Asserting the qualname instead would only re-read what was just written.
        assert resolve("builder", "code-edit") is stand_in
        assert stand_in is not CodeEditBuilder
    finally:
        # Restore, or every later resolution of the builder gets a class with no build().
        Component._registry[("builder", "code-edit")] = CodeEditBuilder

    assert resolve("builder", "code-edit") is CodeEditBuilder


def test_a_broken_third_party_package_does_not_break_unrelated_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Enumeration degrades; resolution still raises, and says why the name is missing."""

    class _BrokenEntryPoint:
        name = "strategy.broken"
        value = "acme_broken.strategy"

        def load(self) -> object:
            raise ImportError("no module named 'acme_broken'")

    monkeypatch.setattr(registry_module, "entry_points", lambda group: [_BrokenEntryPoint()])
    monkeypatch.setattr(registry_module, "_LOAD_FAILURES", {})
    # Restored by monkeypatch: forcing a reload with only the broken entry point visible
    # would otherwise leave discovery marked done, and every later enumeration in this
    # process would short-circuit over a registry that never saw the real components.
    monkeypatch.setattr(registry_module, "_loaded", False)

    load_plugins(force=True)  # must not raise

    with pytest.raises(LookupError, match="failed to import"):
        resolve("strategy", "broken")


def test_get_constructs_with_the_arguments_the_resolver_was_given() -> None:
    """Construction arguments are the consuming strategy's business, not the registry's."""
    seen: dict[str, object] = {}

    class Recording(Builder):
        name = "recording-builder-for-test"
        accepts: ClassVar[frozenset[str]] = frozenset({"code-change"})

        def __init__(self, **kwargs: object) -> None:
            seen.update(kwargs)

    try:
        instance = get_component("builder", "recording-builder-for-test", workspace="/tmp", config=None)

        assert isinstance(instance, Recording)
        assert seen == {"workspace": "/tmp", "config": None}
    finally:
        Component._registry.pop(("builder", "recording-builder-for-test"), None)


def test_a_builder_declares_which_proposal_kinds_it_accepts() -> None:
    """Routing by ``Proposal.kind`` is what lets one run mix candidate kinds later."""
    from nemo_experimentalist_plugin.experimentalist.components.coder import CodeEditBuilder
    from nemo_experimentalist_plugin.experimentalist.components.proposer import CODE_CHANGE

    assert CODE_CHANGE in CodeEditBuilder.accepts
    assert "parameters" not in CodeEditBuilder.accepts


@pytest.mark.asyncio
async def test_the_context_actually_satisfies_the_protocols_it_is_typed_against(tmp_path) -> None:
    """Otherwise the seam is decoration.

    ``roles`` types ``Strategy.run`` and ``Builder.build`` against these Protocols rather
    than the concrete context — naming the implementation there closes an import cycle
    through every component config slice. That indirection is only sound if the real
    context still provides what they name.

    Scope, precisely: ``isinstance`` against a ``runtime_checkable`` Protocol compares
    *attribute names only*. It catches a renamed or deleted verb, which is the drift this
    guards against; it does not catch a changed signature, return type, or sync-vs-async
    flip. ``ty`` covers those at the call sites.
    """
    from doubles import make_context
    from nemo_experimentalist_plugin.experimentalist.seam import BuilderContext, StrategyContext

    ctx = make_context(root=tmp_path)

    assert isinstance(ctx, BuilderContext)
    assert isinstance(ctx, StrategyContext)


def test_agent_class_docstrings_stay_prompt_shaped() -> None:
    """A component Agent's class docstring IS its system prompt.

    nooa's ``_resolve_system_prompt`` walks the MRO and installs the nearest class
    docstring verbatim, so it is spent on the model at every call. Explaining the host's
    design there — Fork, Candidate, ctx.evaluate, reST markup — hands a coding agent
    vocabulary it cannot act on, and nothing else in the suite would notice. Design notes
    belong in comments above the class.
    """
    from nemo_experimentalist_plugin.experimentalist.components.analyzer import TraceRootCauseAnalyzer
    from nemo_experimentalist_plugin.experimentalist.components.coder import CodeEditBuilder
    from nemo_experimentalist_plugin.experimentalist.components.proposer import CodeChangeProposer
    from nemo_experimentalist_plugin.experimentalist.components.selector import ParetoDiversitySelector
    from nemo_experimentalist_plugin.experimentalist.components.terminator import ConvergenceTerminator
    from nemo_experimentalist_plugin.experimentalist.components.trace_scorer import GoalTreeTrajectoryScorer
    from nemo_experimentalist_plugin.experimentalist.strategies.evolutionary import EvolutionaryStrategy

    agents = (
        CodeEditBuilder,
        EvolutionaryStrategy,
        CodeChangeProposer,
        ConvergenceTerminator,
        TraceRootCauseAnalyzer,
        GoalTreeTrajectoryScorer,
        ParetoDiversitySelector,
    )
    for agent in agents:
        prompt = (agent.__doc__ or "").strip()
        assert prompt, f"{agent.__name__} has no system prompt"
        # Length is the blunt guard that catches what a keyword list will not: a prompt
        # that has grown into design documentation is spent on the model at every call.
        assert len(prompt.splitlines()) <= 3, (
            f"{agent.__name__}'s system prompt is {len(prompt.splitlines())} lines; "
            "design notes belong in a comment above the class"
        )
        assert ":class:" not in prompt, f"{agent.__name__}'s prompt carries Sphinx markup"
        for leaked in ("ctx.", "commit_candidate", "BuilderContext", "ExperimentContext", "Candidate", "AAD"):
            assert leaked not in prompt, f"{agent.__name__}'s prompt leaks host vocabulary: {leaked}"


def test_subclassing_a_registered_component_is_allowed() -> None:
    """Extending the built-in CodeEditBuilder is the most obvious way to customise a builder.

    `name` must come from the subclass alone. Inheriting it made `class MyCoder(CodeEditBuilder)`
    look like a second claim on "code-edit" and raise at class-definition time — and because
    `load_plugins` swallows entry-point import errors, the author's whole package would
    have been recorded as a load failure with every component in it unresolvable.
    """
    from nemo_experimentalist_plugin.experimentalist.components.coder import CodeEditBuilder

    class UnnamedSubclass(CodeEditBuilder):  # must not raise
        pass

    assert ("builder", "code-edit") not in {
        (role, name) for (role, name), cls in Component._registry.items() if cls is UnnamedSubclass
    }
    assert resolve("builder", "code-edit") is CodeEditBuilder, "the subclass must not have taken over the name"

    try:

        class NamedSubclass(CodeEditBuilder):
            name = "coder-plus"

        assert resolve("builder", "coder-plus") is NamedSubclass
        assert NamedSubclass.role == "builder", "role is inherited; only name is not"
    finally:
        Component._registry.pop(("builder", "coder-plus"), None)


def test_repeated_metadata_lookups_do_not_re_read_the_whole_store(tmp_path) -> None:
    """The prompts call `get_metadata` once per agent, in a loop.

    Each record carries its full trial list including traces, so re-globbing and
    re-parsing the store per lookup made one report pass quadratic in the population.
    """
    from doubles import make_candidate
    from nemo_experimentalist_plugin.experimentalist.components.tools import WorkspaceTool

    candidates_root = tmp_path / "eval-and-optimize" / "candidates"
    candidates_root.mkdir(parents=True)
    for index in range(5):
        candidate = make_candidate(label=f"agent-{index}", candidate_id=f"id-{index}")
        (candidates_root / f"id-{index}.json").write_text(candidate.model_dump_json())

    from nemo_experimentalist_plugin.experimentalist import experimentalist_backend as backend_module

    loads = 0
    real_load = backend_module.load_candidate

    def _counting_load(path):
        nonlocal loads
        loads += 1
        return real_load(path)

    tool = WorkspaceTool(workspace=tmp_path)
    import unittest.mock

    with unittest.mock.patch.object(backend_module, "load_candidate", _counting_load):
        for index in range(5):
            tool.get_metadata(f"agent-{index}")

    assert loads == 5, f"one pass over the store, not one per lookup; got {loads} reads for 5 lookups"


def test_a_components_class_name_is_its_component_name_plus_its_role() -> None:
    """`<Component><Role>` — `code-edit` + `builder` is `CodeEditBuilder`.

    Derived rather than listed, so a component added later is covered without anyone
    remembering to extend this. The rule earns its strictness twice over:

    * It is reversible. A reader holding `builder: code-edit` from a config file can name
      the class without grepping, and someone reading a traceback can name the config
      value that selected it.
    * It keeps role and implementation apart. The component classes were called
      `Proposer` and `Terminator` -- the same names as `roles.Proposer` and
      `roles.Terminator`, distinguishable only by import path, which reads as though each
      role has exactly one possible implementation. That is the opposite of what this
      registry is for.

    Shortening is what makes a convention decorative, so there are no exceptions:
    `harbor` + `outcome-evaluator` is `HarborNativeOutcomeEvaluator`, not `HarborEvaluator`.
    """
    from nemo_experimentalist_plugin.experimentalist.registry import Component, load_plugins

    load_plugins()
    assert Component._registry, "nothing registered; the check would pass vacuously"

    def expected(component: str, role: str) -> str:
        parts = component.split("-") + role.split("-")
        return "".join(part[:1].upper() + part[1:] for part in parts)

    # Shipped components only. The registry is global and other tests register doubles
    # into it, so an unfiltered sweep fails on whichever of those ran first.
    wrong = {
        f"{role}:{name}": f"{cls.__name__} (expected {expected(name, role)})"
        for (role, name), cls in Component._registry.items()
        if cls.__module__.startswith("nemo_experimentalist_plugin.") and cls.__name__ != expected(name, role)
    }
    assert len(Component._registry) >= 9, "fewer components than this package ships; the filter is too tight"

    assert not wrong, f"class names that do not follow <Component><Role>: {wrong}"
