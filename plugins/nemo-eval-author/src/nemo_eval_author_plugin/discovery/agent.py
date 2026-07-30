# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A bounded scout that proposes a config when the ladder cannot get one.

Only reached when validation failed on something a look around the repo could plausibly
settle: which directory is the dataset rather than the single-task template, what the
wrapper's class is actually called, which of two plausible entrypoints is the real one.

The scout's output is a proposal and never a result. Whatever it returns goes back through
the ladder from the schema rung, and a config it touched is persisted only if Harbor then
accepts it. That ordering is the whole reason a later, weaker model can trust the artifact:
the strong model is allowed to guess, and Harbor decides whether the guess was right.

Importing this module builds an LLM client, because ``Agent`` binds ``llm`` while the class
body executes. The CLI therefore imports it inside the command body rather than at module
scope, so ``nemo eval-author discover`` on a repo that needs no scouting works with no
``AUTHOR_*`` credentials at all.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

# Populates EXPERIMENTALIST_* from AUTHOR_*, which the Experimentalist modules imported
# below read while their class bodies execute. Must stay ahead of them; isort keeps it there.
import nemo_eval_author_plugin._env_bridge  # noqa: F401
from nemo_eval_author_plugin.discovery.models import CandidateConfig, ConfigSource, Finding
from nemo_eval_author_plugin.discovery.validate import ValidationOutcome, run_ladder
from nemo_eval_author_plugin.model_config import get_smart_model
from nemo_experimentalist_plugin.experimentalist.components.tools import GuardedShellTools
from nooa import Agent, CodeActStrategy, strategy
from nooa.config import CodeActConfig
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_GROUP = "scout"

# The rungs a look at the filesystem could plausibly resolve. A backend preflight failure
# means Docker is not running, and no amount of reading the repo fixes that.
_SCOUTABLE_RUNGS = frozenset({"schema", "resolution", "tasks", "agent", "config-source"})

ProposeFn = Callable[[CandidateConfig, list[Finding], Path], Awaitable["ScoutProposal"]]


class ScoutProposal(BaseModel):
    """A config the scout believes will validate, plus its reasoning."""

    config: dict[str, Any] = Field(description="A complete Harbor job config payload, not a patch.")
    rationale: str = Field(description="What was inspected and why this config follows from it.")
    changed: list[str] = Field(default_factory=list, description="The keys that differ from the input config.")


class DiscoveryScout(Agent, llm=get_smart_model()):
    """Reads an agent repository to work out how its Harbor evaluations are meant to run."""

    def __init__(self, repo_root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.repo_root = repo_root
        self.shell = GuardedShellTools(cwd=repo_root)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=20, cell_timeout=60.0)))
    async def propose_config(self, candidate: str, blocking: str) -> ScoutProposal:
        """Work out the Harbor job config this repository actually intends.

        A candidate config was assembled from the repository and rejected by Harbor's own
        validators. Use the shell to inspect the repository and return a config that will
        pass.

        Args:
            candidate: The rejected Harbor job config, as JSON.
            blocking: The validation failures, each naming the Harbor call that produced it.

        Returns:
            ScoutProposal: A complete config payload, the keys changed, and the reasoning.

        Ground every change in something read from the filesystem: a directory that holds
        `task.toml` files, a class definition in a wrapper module, a path named in a config
        or README. Do not invent dataset paths, task names, agent import paths, or model
        names, and do not add fields the repository gives no evidence for.

        A config returned unchanged with the rationale explaining what is missing is a
        useful answer. A plausible-looking guess is not: this proposal is revalidated
        against Harbor, and a wrong guess costs another round trip while an honest "the
        repository does not say" tells the user what to fix.
        """

    async def scout(self, candidate: CandidateConfig, blocking: list[Finding]) -> ScoutProposal:
        summary = "\n".join(
            f"- {finding.name}: {finding.message}" + (f" (from {finding.harbor_call})" if finding.harbor_call else "")
            for finding in blocking
        )
        return await self.propose_config(json.dumps(candidate.data, indent=2, sort_keys=True), summary)


def is_scoutable(outcome: ValidationOutcome) -> bool:
    """Whether any failure is the kind reading the repo could plausibly settle."""
    return any(finding.name in _SCOUTABLE_RUNGS for finding in outcome.findings if finding.status == "fail")


async def _ask_the_scout(candidate: CandidateConfig, blocking: list[Finding], repo_root: Path) -> ScoutProposal:
    return await DiscoveryScout(repo_root=repo_root).scout(candidate, blocking)


async def attempt_repair(
    candidate: CandidateConfig,
    outcome: ValidationOutcome,
    repo_root: Path,
    propose: ProposeFn = _ask_the_scout,
) -> tuple[CandidateConfig, ValidationOutcome, list[Finding]]:
    """Let the scout propose a config, then make Harbor judge it.

    Returns the proposal and its validation only if the ladder is happier with it than
    with what we had. "Happier" means runnable, not merely different: a proposal that
    trades one failure for another is noise, and keeping the original at least leaves the
    user with failures traceable to their own repo rather than to a language model.

    ``propose`` is a parameter so this containment logic can be tested without a model.
    It is the part worth testing: nooa refuses to let a test attach a method to an agent
    class, and the interesting behavior here is what happens to a proposal, not how one is
    produced.
    """
    blocking = [finding for finding in outcome.findings if finding.status == "fail"]
    try:
        proposal = await propose(candidate, blocking, repo_root)
    except Exception as exc:
        logger.debug("discovery scout failed", exc_info=True)
        return (
            candidate,
            outcome,
            [
                Finding(
                    name="scout",
                    group=_GROUP,
                    status="warn",
                    message=f"The scout could not run: {type(exc).__name__}: {exc}",
                    hint="Set AUTHOR_API_KEY and AUTHOR_BASE_URL, or pass --no-deep to skip this step.",
                    provenance="inference",
                )
            ],
        )

    if proposal.config == candidate.data:
        return (
            candidate,
            outcome,
            [
                Finding(
                    name="scout",
                    group=_GROUP,
                    status="warn",
                    message=f"The scout found nothing in the repo to change: {proposal.rationale}",
                    provenance="inference",
                )
            ],
        )

    proposed = CandidateConfig(
        data=proposal.config,
        source=ConfigSource(
            kind=candidate.source.kind,
            detail=f"{candidate.source.detail}, then adjusted by the discovery scout",
            path=candidate.source.path,
        ),
    )
    revalidated = await run_ladder(proposed, repo_root)
    changed = ", ".join(proposal.changed) if proposal.changed else "unspecified keys"

    if not revalidated.runnable:
        return (
            candidate,
            outcome,
            [
                Finding(
                    name="scout",
                    group=_GROUP,
                    status="warn",
                    message=f"The scout proposed changes to {changed}, and Harbor still rejected the result",
                    hint=f"Its reasoning: {proposal.rationale}",
                    provenance="inference",
                )
            ],
        )

    return (
        proposed,
        revalidated,
        [
            Finding(
                name="scout",
                group=_GROUP,
                status="pass",
                message=f"The scout changed {changed}, and Harbor accepted the result",
                hint=f"Its reasoning: {proposal.rationale}",
                provenance="inference",
            )
        ],
    )
