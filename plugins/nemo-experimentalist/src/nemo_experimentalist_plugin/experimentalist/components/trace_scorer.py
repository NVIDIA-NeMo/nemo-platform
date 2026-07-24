# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import logging
from pathlib import Path
from typing import Any

from nemo_experimentalist_plugin.experimentalist.components.evaluator import Dataset, TrialResult
from nemo_platform import AsyncNeMoPlatform
from nooa import Agent, CodeActStrategy, strategy
from nooa.agentdoc import doc
from nooa.config import CodeActConfig
from pydantic import BaseModel, Field

from .goal_tree import GoalNode
from .model_config import get_mid_model
from .trace_explorer import TraceExplorer  # noqa: F401

logger = logging.getLogger(__name__)


class GroupLeafScore(BaseModel):
    """A numeric score and qualitative reason for a single agent on a goal-tree leaf."""

    score: float = Field(ge=0.0, le=1.0)
    reason: str
    span_ids: list[str] = Field(
        default_factory=list,
        description="Span IDs from the trace that contain the key evidence cited in `reason`.",
    )


class GroupLeafScorer(Agent):
    """Score a group of agent traces against a goal-tree leaf node."""

    def __init__(
        self,
        workspace: Path,
        llm: Any | None = None,
        client: AsyncNeMoPlatform | None = None,
        nmp_workspace: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the scorer for the given workspace.

        Args:
            workspace: Path to the workspace directory.
            llm: Language model instance; defaults to mid-tier model selection.
            client: NeMo Platform client; required to load ``intake://`` traces.
            nmp_workspace: NeMo Platform workspace name; required to load ``intake://`` traces.
            **kwargs: Additional arguments passed to parent Agent class.

        Raises:
            ValueError: if workspace does not exist or is invalid.

        """
        super().__init__(llm=llm or get_mid_model(), **kwargs)
        self.workspace = workspace
        self._client = client
        self._nmp_workspace = nmp_workspace
        self.context["trace_explorer_documentation"] = doc(TraceExplorer)

    @strategy(CodeActStrategy(config=CodeActConfig(max_iterations=15, cell_timeout=120.0)))
    async def run(
        self,
        node: GoalNode,
        trials: dict[str, TrialResult],
        dataset: Dataset,
    ) -> dict[str, GroupLeafScore]:  # pyright: ignore[reportReturnType]
        """Compute the relative group advantage score for a group of traces coming from different agents for a given node.
        All scores must be strictly ordered: score_a < score_b < ... < score_n (no ties).

        Args:
            node: The node to score. Contains the goal description and the expected output.
            trials: Trials to score.  Each TrialResult carries a ``trace`` reference and a
                ``metrics`` dict populated by the task evaluator (e.g. ``{"score": 0.82}``).
                Metrics reflect overall task success — do NOT use them for scoring.
            dataset: The dataset to score.

        ## Loading traces

        Load each trace with
        `await TraceExplorer.from_ref(trial.trace, self._client, self._nmp_workspace)`.
        If the trace is not available, skip the trial.

        Use TraceExplorer to inspect the full span hierarchy: sessions, turns, LLM messages, tool
        calls, code execution outputs, sub-agent spans, errors, and observations.
        All TraceExplorer query methods are async — await them.
        Descend into sub-agent spans; key evidence is often buried inside nested agents, not in the root span.

        ## Scoring against the goal node

        Score each agent *exclusively* on how well its trace satisfies `node.goal`.
        Do NOT use `trial.metrics` to determine or adjust scores — `TrialResult.metrics`
        are task-level outcome signals, not node-level evidence.  Never mention metric values
        in reasoning as justification for a score.

        Apply proportional partial credit:
        - Agent performs all required steps correctly → 0.8–1.0
        - Agent performs most steps correctly but fails or skips one key requirement → 0.5–0.7
        - Agent attempts the right approach but with significant errors that undermine the goal → 0.2–0.4
        - Agent does not address the goal or uses a fundamentally wrong approach → 0.0–0.2

        ## Writing reasons and grounding span IDs

        Each reason must cite specific evidence observed in the trace — exact function names, tool outputs,
        quoted values, or code snippets that directly relate to `node.goal`.  Generic descriptions
        ("the agent tried X") are not sufficient.  Good examples:
        - "trace shows readUInt32BE at offset 24 → 0x400520, matching ELF e_entry"
        - "grepped /app/morpheus for ImageMath imports, found zero matches in source files"
        - "WritingAgent output lists five domains: daily life, workplace, marriage, parenting, emotional well-being"

        Bad (insufficient):
        - "the agent verified the package version"
        - "trace shows the agent covered the required domains"

        Also populate `span_ids` with the IDs of the spans that contain the key evidence you cited.
        Span IDs MUST be retrieved from TraceExplorer (e.g. `await explorer.get_spans()`) and
        copied verbatim from the returned objects — never abbreviated, guessed, or constructed from
        the overview text.  Include only spans that directly support the score — not every span.

        Returns:
            dict[str, GroupLeafScore]: scores indexed by agent ID; each entry includes a numeric
            score, a reason citing specific trace evidence, and the span IDs that ground the reason.
        """
        explorers: dict[str, TraceExplorer] = {}
        for agent_id, trial in trials.items():
            if not trial.trace:
                continue
            explorer = await TraceExplorer.from_ref(trial.trace, self._client, self._nmp_workspace)
            explorers[agent_id] = explorer
            print(f"Agent {agent_id} trace overview:")
            print(await explorer.get_overview())
            print(await explorer.get_errors())
        ...
