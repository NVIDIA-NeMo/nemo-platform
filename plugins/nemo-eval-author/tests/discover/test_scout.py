# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The scout proposes; Harbor decides.

This is the seam where a language model's guess enters an artifact a later agent is told to
trust, so the tests here are about containment rather than about the model. The scout's
output is pushed back through the same ladder, a proposal Harbor rejects changes nothing,
and anything it did influence is marked as inference so a reader can tell it apart from a
verdict Harbor returned.

No model is ever called: ``attempt_repair`` takes the proposal function as a parameter and
these tests pass a fixed one. A test that reached a real model would need credentials and
would assert on something nondeterministic.
"""

from harbor_fixtures import MENTIONS_REWARD_IN_COMMENT, write_dataset
from nemo_eval_author_plugin.discovery import validate
from nemo_eval_author_plugin.discovery.agent import ProposeFn, ScoutProposal, attempt_repair, is_scoutable
from nemo_eval_author_plugin.discovery.models import CandidateConfig, ConfigSource, Finding


def _candidate(data: dict) -> CandidateConfig:
    return CandidateConfig(data=data, source=ConfigSource(kind="convention", detail="inferred from task dirs"))


def _outcome(*failures: str) -> validate.ValidationOutcome:
    return validate.ValidationOutcome(
        findings=[
            Finding(name=name, group="validation", status="fail", message="broken", provenance="harbor")
            for name in failures
        ]
    )


def _proposes(proposal: ScoutProposal | Exception) -> ProposeFn:
    async def propose(candidate, blocking, repo_root):
        if isinstance(proposal, Exception):
            raise proposal
        return proposal

    return propose


def test_only_failures_a_look_at_the_repo_could_settle_are_scoutable():
    assert is_scoutable(_outcome("resolution")) is True
    assert is_scoutable(_outcome("agent")) is True
    # Docker not running is a fact about the machine; no amount of reading the repo helps.
    assert is_scoutable(_outcome("backend")) is False
    assert is_scoutable(_outcome("reward")) is False


async def test_a_proposal_harbor_accepts_is_adopted_and_labelled(tmp_path):
    good = write_dataset(tmp_path / "evals" / "validation", count=1)
    broken = _candidate({"datasets": [{"path": str(tmp_path / "wrong-place")}]})
    outcome = await validate.run_ladder(broken, tmp_path)
    assert not outcome.runnable
    propose = _proposes(
        ScoutProposal(
            config={"datasets": [{"path": str(good)}]},
            rationale="evals/validation holds the task.toml dirs",
            changed=["datasets"],
        )
    )

    candidate, revalidated, findings = await attempt_repair(broken, outcome, tmp_path, propose)

    assert candidate.data["datasets"] == [{"path": str(good)}]
    assert revalidated.runnable
    # The config's provenance has to admit a model touched it, which is also what stops the
    # artifact from telling a later run to use the repo's own file.
    assert "adjusted by the discovery scout" in candidate.source.detail
    assert candidate.source.adjusted is True
    assert findings[0].status == "pass"
    assert findings[0].provenance == "inference"


async def test_a_proposal_harbor_rejects_changes_nothing(tmp_path):
    """Otherwise a plausible guess could replace failures the user could act on."""
    broken = _candidate({"datasets": [{"path": str(tmp_path / "wrong-place")}]})
    outcome = await validate.run_ladder(broken, tmp_path)
    propose = _proposes(
        ScoutProposal(
            config={"datasets": [{"path": str(tmp_path / "also-wrong")}]},
            rationale="guessing",
            changed=["datasets"],
        )
    )

    candidate, revalidated, findings = await attempt_repair(broken, outcome, tmp_path, propose)

    assert candidate is broken
    assert revalidated is outcome
    assert findings[0].status == "warn"
    assert "still rejected" in findings[0].message


async def test_a_proposal_that_only_fixes_one_of_two_failures_is_not_adopted(tmp_path):
    """Runnable is the bar, not merely different: a partial fix is still not runnable."""
    dataset = write_dataset(tmp_path / "evals" / "validation", count=1, test_script=MENTIONS_REWARD_IN_COMMENT)
    broken = _candidate({"datasets": [{"path": str(tmp_path / "wrong-place")}]})
    outcome = await validate.run_ladder(broken, tmp_path)
    propose = _proposes(
        ScoutProposal(config={"datasets": [{"path": str(dataset)}]}, rationale="found the dir", changed=["datasets"])
    )

    candidate, _, findings = await attempt_repair(broken, outcome, tmp_path, propose)

    assert candidate is broken, "the reward contract is still broken, so nothing is adopted"
    assert findings[0].status == "warn"


async def test_a_scout_with_nothing_to_change_says_so(tmp_path):
    broken = _candidate({"datasets": [{"path": str(tmp_path / "wrong-place")}]})
    outcome = await validate.run_ladder(broken, tmp_path)
    propose = _proposes(ScoutProposal(config=broken.data, rationale="the repo names no dataset anywhere", changed=[]))

    candidate, revalidated, findings = await attempt_repair(broken, outcome, tmp_path, propose)

    assert candidate is broken
    assert revalidated is outcome
    assert "nothing in the repo to change" in findings[0].message
    assert "names no dataset" in findings[0].message


async def test_a_scout_that_cannot_run_degrades_to_a_warning(tmp_path):
    """Missing credentials must not turn a reportable failure into a crash."""
    broken = _candidate({"datasets": [{"path": str(tmp_path / "wrong-place")}]})
    outcome = await validate.run_ladder(broken, tmp_path)
    propose = _proposes(RuntimeError("no model credentials"))

    candidate, revalidated, findings = await attempt_repair(broken, outcome, tmp_path, propose)

    assert candidate is broken
    assert revalidated is outcome
    assert findings[0].status == "warn"
    assert findings[0].hint is not None and "--dangerously-fix" in findings[0].hint
