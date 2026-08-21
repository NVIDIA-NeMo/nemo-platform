# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NeMo Insights analyst agent, built on NVIDIA NeMo OO Agents.

The analyst inspects recent traces from a target agent, identifies failure
patterns and performance regressions, and reports actionable Insights. It is a
Nooa :class:`~nooa.Agent` with a fixed persona (``INSTRUCTIONS``) and scoped,
read-only methods for observability data.

Rather than mutating platform state mid-run through a series of write tools,
the analyst gathers evidence with its read tools and then emits a single
:class:`~nemo_insights_plugin.analyst.result.AnalystResult` as its typed
output. Producing that result ends the run and hands the entire change-set
(new insights and updates) back to the CLI, which is the only component
that persists.

The result is delivered through Nooa's ``return_result`` helper and validated
against the ``AnalystResult`` schema.

The analyst's persona, task, the agent-under-test name, and the optional AUT
spec are all formatted into the instructions by ``build_analyst_agent``; the
run is seeded with only the minimal ``KICKOFF`` request. The per-run config the
methods need is carried in :class:`~nemo_insights_plugin.analyst.deps.AnalystDeps`.
Workspace and base URL aren't in the instructions because the methods are already
scoped to them via ``AnalystDeps``.
"""

from typing import Annotated, Any

from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.functions import insights, traces
from nemo_insights_plugin.analyst.result import AnalystResult
from nemo_platform_plugin.nooa_model_client import get_default_model, get_fast_model
from nooa import Agent, CodeActStrategy, hidden, strategy
from nooa.agents import TokenBudgetSummarizer
from nooa.config import CodeActConfig
from nooa.config.summarizer_config import TokenBudgetConfig
from nooa.tools import TodoManager
from nooa.unifiedllm import UnifiedLLM

# Safety cap on model requests per run so a misbehaving loop cannot spin
# forever. Each tool-calling round is one request, so this bounds the analyst
# to roughly this many tool-use steps.
MAX_REQUESTS = 50
MAX_SUMMARY_TOKENS = 80_000

# ---------------------------------------------------------------------------
# Analyst persona + task + methodology, derived from docs/prd-por.md.
#
# This is the analyst context prompt and the only long-form prompt
# the analyst gets — there is no separate user-message brief. ``{agent}`` is
# formatted in by ``build_analyst_agent`` and the optional AUT spec is appended
# as the final paragraph. Nooa owns the CodeAct protocol and method catalog, so
# this text covers only the analyst's persona,
# principles, and method — it deliberately does not document the tools or
# restate any output format.
#
# This is v0 — untuned against real traces; treat early output as preliminary.
# ---------------------------------------------------------------------------
INSTRUCTIONS = """
You are the Analyst agent for the NeMo Insights plugin. Analyze recent
production and evaluation traces from the agent under test (AUT),
**{agent}**, and file Insights for the highest-impact recurring failure
patterns you find. An Insight must be specific enough to act on and general
enough to recur. A noisy Insight is worse than no Insight.

## Operating principles

1. Quality over quantity. Two precise, well-evidenced Insights beat ten vague
   ones. Name the failure mode, affected component, and triggering conditions.
2. Traces are receipts. Every Insight must cite the ``id`` of each evidence
   trace returned by the trace tools. Aim for at least three representative
   traces before filing a recurring pattern.
3. Prioritize negative user or developer feedback, explicit errors, evaluator
   regressions, latency or cost outliers, and divergence from the agent spec,
   in that order. Prefer patterns spread across multiple traces.
4. Do not duplicate. Check existing Insights before filing. Append new trace
   evidence to an existing open Insight instead of creating a near-duplicate.

## Method

1. Call ``filter_traces`` first to survey a broad set of lightweight trace
   summaries. Start with error traces, then inspect a broader sample.
2. Call ``read_traces`` with bounded batches of interesting trace IDs. Process
   the returned traces row by row and cluster recurring failures across rows.
   Each row has ``id`` plus a provider-native ``data`` object. Inspect that
   object rather than assuming one universal span schema. It includes the
   trace's detailed execution records and available feedback/evaluation
   signals.
3. Trace a candidate failure through its model/tool execution records and
   feedback before treating it as evidence. Do not infer root cause from a
   summary alone.
4. Check existing Insights so you know which findings are new and which add
   evidence to an existing Insight.

## Reporting your findings

When analysis is complete, return one ``AnalystResult`` with the full
change-set:

- ``new_insights``: new problems, each with a short title, actionable
  description, and evidence trace IDs.
- ``updated_insights``: evidence for existing Insights. Reference the target
  by its store-assigned ``id`` and append only trace IDs.

Producing the result ends the run. If nothing meets the evidence bar, return
empty lists and explain that in the summary. Do not call the agent "the AUT"
in developer-facing Insights.
"""


AGENT_SPEC_HEADER = """
## Agent Spec

Use this as the contract for what the agent is supposed to do, what
success looks like, and what behavior should be flagged as divergence.
Flag agent divergence from the spec. The spec was authored by the
developer of the application and should be considered the purpose and goals.
"""

KICKOFF = (
    "Analyze recent traces for the agent under test and file Insights for the highest-impact failure patterns you find."
)


class Analyst(Agent):
    """Analyze telemetry using only scoped, read-only NeMo Insights methods."""

    _deps: Annotated[AnalystDeps, hidden]

    def __init__(
        self,
        *,
        deps: AnalystDeps,
        agent: str,
        agent_spec: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(llm=kwargs.pop("llm", None) or get_default_model(), **kwargs)
        self._deps = deps
        self.todos = TodoManager()
        TokenBudgetSummarizer.install(
            self,
            llm=get_fast_model(),
            config=TokenBudgetConfig(max_tokens=MAX_SUMMARY_TOKENS),
        )

        instructions = INSTRUCTIONS.format(agent=agent)
        if agent_spec and agent_spec.strip():
            instructions = f"{instructions}\n{AGENT_SPEC_HEADER}\n\n{agent_spec.strip()}\n"
        self.context["analyst_instructions"] = instructions

    async def filter_traces(
        self,
        trace_ids: list[str] | None = None,
        started_after: str | None = None,
        started_before: str | None = None,
        has_error: bool | None = None,
        limit: int = 100,
    ) -> dict[str, object]:
        """List lightweight traces from the configured provider.

        Returns trace IDs and provider-native summary blobs. ``truncated``
        means more traces matched than were returned.

        Args:
            trace_ids: Optional provider-native trace IDs to resolve.
            started_after: Optional inclusive ISO 8601 lower time bound.
            started_before: Optional inclusive ISO 8601 upper time bound.
            has_error: True for failed traces, False for successful traces,
                or None for either.
            limit: Maximum trace refs to return, clamped to the run ceiling.
        """
        return await traces.filter_traces(
            self._deps,
            trace_ids=trace_ids,
            started_after=started_after,
            started_before=started_before,
            has_error=has_error,
            limit=limit,
        )

    async def read_traces(self, trace_ids: list[str]) -> dict[str, object]:
        """Hydrate traces row by row from the configured provider.

        Each returned row has ``id`` and a provider-native ``data`` blob. For
        Intake the blob contains the trace, spans, annotations, and evaluator
        results. For LangSmith it contains the run tree and feedback. For
        MLflow it contains the native trace info, spans, and assessments.

        Args:
            trace_ids: Provider-native IDs returned by ``filter_traces``.
        """
        return await traces.read_traces(self._deps, trace_ids=trace_ids)

    async def list_insights(
        self,
        agent: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> str:
        """List existing Insights for the agent under test.

        Use this before deciding whether a finding is a new Insight or new
        evidence for an existing one.

        Args:
            agent: Filter by agent name. Defaults to the analyst's configured
                agent; pass an empty string to list across agents.
            status: Filter by lifecycle status.
            page: Page number (1-indexed).
            page_size: Items per page.
        """
        return await insights.list_insights(
            self._deps,
            agent=agent,
            status=status,
            page=page,
            page_size=page_size,
        )

    @strategy(
        CodeActStrategy(
            config=CodeActConfig(
                max_iterations=MAX_REQUESTS,
                cell_timeout=3600.0,
            )
        )
    )
    async def analyze(self, request: str) -> AnalystResult:  # ty: ignore[empty-body]  # pyright: ignore[reportReturnType]
        """Analyze the target agent's traces and return one complete change-set.

        Follow ``self.context["analyst_instructions"]``. Gather evidence with
        the scoped read-only methods on ``self``. When the analysis is complete,
        call ``return_result(result=AnalystResult(...))`` exactly once.

        Args:
            request: The analysis request.

        Returns:
            The complete set of new Insights and evidence updates.
        """
        ...


def build_analyst_agent(
    *,
    deps: AnalystDeps,
    agent: str,
    agent_spec: str | None = None,
    llm: UnifiedLLM | None = None,
    **kwargs: Any,
) -> Analyst:
    """Build the analyst with per-run scope and optional Nooa runtime overrides."""
    return Analyst(
        deps=deps,
        agent=agent,
        agent_spec=agent_spec,
        llm=llm,
        **kwargs,
    )
