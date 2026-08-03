# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The candidate contract: allocate → build → commit, and what commit refuses.

A Candidate exists only once its artifact does, so nothing durable can point at partial
work. These cover the three ways that could be violated — committing a missing artifact,
committing one outside the run's candidate root, and letting the derived projections
drift from the Proposal they came from.
"""

from pathlib import Path

import pytest
from doubles import FakeBackend, make_candidate, make_context
from nemo_experimentalist_plugin.entities import Candidate, Proposal, ResourceRef


def _proposal(ancestor: str | None = "agent-0") -> Proposal:
    return Proposal(
        ancestor=ancestor,
        description="add a retrieval step before the planner",
        kind="code-change",
        payload={"optimization_type": "add_method", "task_ids": ["task-1"]},
    )


@pytest.mark.asyncio
async def test_forking_the_baseline_copies_the_agent_under_test(tmp_path: Path) -> None:
    ctx = make_context(root=tmp_path)
    (ctx.agent_dir / "main.py").write_text("print('hello')\n")

    forked = await ctx.fork(None)

    assert forked.name == "agent-0"
    assert (forked / "main.py").read_text() == "print('hello')\n"


@pytest.mark.asyncio
async def test_a_fork_carries_no_owners_scaffolding(tmp_path: Path) -> None:
    """The ignore set is composed from three owners, so no one list can strip too much."""
    ctx = make_context(root=tmp_path)
    (ctx.agent_dir / "main.py").write_text("keep me\n")
    for name in ("__pycache__", ".venv", "dataset", "eval-and-optimize", "my-traces"):
        (ctx.agent_dir / name).mkdir()

    forked = await ctx.fork(None)

    assert (forked / "main.py").exists()
    for name in ("__pycache__", ".venv", "dataset", "eval-and-optimize", "my-traces"):
        assert not (forked / name).exists(), name


@pytest.mark.asyncio
async def test_forking_a_proposal_branches_from_its_ancestors_artifact(tmp_path: Path) -> None:
    """The ancestor is resolved through its stored artifact, not by treating its id as a path."""
    backend = FakeBackend()
    ctx = make_context(root=tmp_path, backend=backend)
    baseline = await ctx.commit_candidate(proposal=None, artifact=await ctx.fork(None), description="baseline")
    (ctx.candidate_dir(baseline) / "main.py").write_text("ancestor code\n")

    forked = await ctx.fork(_proposal(ancestor=baseline.id))

    assert forked.name == "agent-1"
    assert (forked / "main.py").read_text() == "ancestor code\n"


@pytest.mark.asyncio
async def test_committing_derives_lineage_and_description_from_the_proposal(tmp_path: Path) -> None:
    ctx = make_context(root=tmp_path)
    await ctx.commit_candidate(proposal=None, artifact=await ctx.fork(None), description="baseline")
    proposal = _proposal()
    built = await ctx.fork(proposal)

    candidate = await ctx.commit_candidate(proposal=proposal, artifact=built, generation=1)

    assert candidate.ancestor == "agent-0"
    assert candidate.description == proposal.description
    assert candidate.generated_from == proposal
    assert candidate.generation == 1
    assert candidate.artifact.uri == built.resolve().as_uri()
    assert not candidate.is_baseline


@pytest.mark.asyncio
async def test_a_description_may_not_be_passed_alongside_a_proposal(tmp_path: Path) -> None:
    """Two accounts of one candidate's origin must not be able to drift apart."""
    ctx = make_context(root=tmp_path)
    proposal = _proposal(ancestor=None)

    with pytest.raises(ValueError, match="derived from the Proposal"):
        await ctx.commit_candidate(proposal=proposal, artifact=await ctx.fork(proposal), description="something else")


@pytest.mark.asyncio
async def test_committing_without_a_proposal_requires_a_description(tmp_path: Path) -> None:
    ctx = make_context(root=tmp_path)

    with pytest.raises(ValueError, match="requires an explicit description"):
        await ctx.commit_candidate(proposal=None, artifact=await ctx.fork(None))


@pytest.mark.asyncio
async def test_committing_a_missing_artifact_is_refused(tmp_path: Path) -> None:
    ctx = make_context(root=tmp_path)

    with pytest.raises(ValueError, match="does not exist"):
        await ctx.commit_candidate(
            proposal=None,
            artifact=tmp_path / "eval-and-optimize" / "agents" / "never-written",
            description="baseline",
        )


@pytest.mark.asyncio
async def test_an_artifact_outside_the_candidate_root_is_refused(tmp_path: Path) -> None:
    """The runner must be able to archive and publish every candidate without help."""
    ctx = make_context(root=tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    with pytest.raises(ValueError, match="must live under"):
        await ctx.commit_candidate(proposal=None, artifact=elsewhere, description="baseline")


@pytest.mark.asyncio
async def test_allocate_reserves_a_file_inside_the_candidate_root(tmp_path: Path) -> None:
    """A strategy whose evaluation consumes a file directly gets a path, not a directory."""
    ctx = make_context(root=tmp_path)
    proposal = _proposal(ancestor=None)

    path = await ctx.allocate(proposal, filename="optimized_program.json")
    path.write_text("{}")
    candidate = await ctx.commit_candidate(proposal=proposal, artifact=path)

    assert candidate.artifact.uri.endswith("/agent-0/optimized_program.json")
    assert ctx.candidate_dir(candidate) == path.parent


@pytest.mark.asyncio
async def test_allocate_refuses_a_path_rather_than_a_name(tmp_path: Path) -> None:
    ctx = make_context(root=tmp_path)

    with pytest.raises(ValueError, match="bare filename"):
        await ctx.allocate(None, filename="../escape.json")


def test_a_candidate_whose_projections_drift_from_its_origin_is_invalid() -> None:
    proposal = _proposal()

    with pytest.raises(ValueError, match="disagrees with its Proposal"):
        Candidate(
            label="agent-1",
            run_id="run-1",
            ancestor="somewhere-else",
            generated_from=proposal,
            description=proposal.description,
            artifact=ResourceRef(uri="file:///tmp/agent-1"),
        )


def test_the_baseline_is_the_one_without_an_ancestor() -> None:
    assert make_candidate(label="agent-0").is_baseline
    assert not make_candidate(label="agent-1", ancestor="agent-0").is_baseline


@pytest.mark.asyncio
async def test_candidates_are_listed_from_the_store_not_from_a_directory_walk(tmp_path: Path) -> None:
    """A strategy that does not produce one directory per candidate can still list them."""
    from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import LocalExperimentalistBackend

    backend = LocalExperimentalistBackend(path=tmp_path)
    ctx = make_context(root=tmp_path, backend=backend)
    proposal = _proposal(ancestor=None)
    path = await ctx.allocate(proposal, filename="optimized_program.json")
    path.write_text("{}")
    committed = await ctx.commit_candidate(proposal=proposal, artifact=path)

    listed = await ctx.candidates()

    assert [c.id for c in listed] == [committed.id]
    assert (tmp_path / "eval-and-optimize" / "candidates" / f"{committed.id}.json").is_file()
    # Metadata never lands inside the artifact it describes.
    assert not (path.parent / "metadata.json").exists()


@pytest.mark.asyncio
async def test_a_fork_does_not_inherit_the_ancestors_architecture_doc(tmp_path: Path) -> None:
    """The Builder is told its directory holds the ancestor's source and nothing else.

    `architecture.md` describes the ancestor, not the candidate. Inheriting it makes that
    statement false at the moment the Builder reads it, and hands a code-writing agent a
    description that no longer matches what it is about to change. The Coder re-seeds it
    from the ancestor afterwards, to edit in place against the finished source.
    """
    backend = FakeBackend()
    ctx = make_context(root=tmp_path, backend=backend)
    baseline = await ctx.commit_candidate(proposal=None, artifact=await ctx.fork(None), description="baseline")
    ancestor_dir = ctx.candidate_dir(baseline)
    (ancestor_dir / "main.py").write_text("print('ancestor')\n")
    (ancestor_dir / "architecture.md").write_text("# describes agent-0\n")

    forked = await ctx.fork(_proposal(ancestor=baseline.id))

    assert (forked / "main.py").read_text() == "print('ancestor')\n"
    assert not (forked / "architecture.md").exists()
