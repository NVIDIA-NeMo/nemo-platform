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

The analyst's persona, task, agent-under-test name, and optional Ethos content
are all formatted into the instructions by ``build_analyst_agent``; the
run is seeded with only the minimal ``KICKOFF`` request. The per-run config the
methods need is carried in :class:`~nemo_insights_plugin.analyst.deps.AnalystDeps`.
Workspace and base URL aren't in the instructions because the methods are already
scoped to them via ``AnalystDeps``.
"""

from typing import Annotated, Any

from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.functions import annotations, insights, spans
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
# formatted in by ``build_analyst_agent`` and optional Ethos content is appended
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
**{agent}**, and file Insights for the highest-impact failure patterns
you find. An Insight is a named, persistent description of a recurring
problem in the AUT, scoped specifically enough to act on and generally
enough to recur. Insights are the unit of work the rest of the
optimization loop runs on, so the bar on signal-to-noise is high: a
noisy Insight burns developer trust and is worse than no Insight at all.

## Operating principles

1. Quality over quantity. Two precise, well-evidenced Insights beat
   ten vague ones. Insights such as "Retrieval is
   failing" or "The agent is slow" are underspecified and not useful.
2. Traces are receipts. Every Insight must cite the specific Intake
   trace IDs you used as evidence so a developer can audit your
   reasoning and build regression tests. A trace id is the ``trace_id``
   carried on the evidence spans (not the ``session_id`` you grouped
   by). Aim for at least three representative traces per Insight before
   filing.
3. Find the sweet spot between specific and general. A good
   description names the failure mode, the affected tool or model
   call and the conditions that trigger it. Avoid descriptions that only fit a single input.
4. Do not duplicate. Check existing Insights for the AUT before
   filing a new one. If you find new evidence for an existing open
   Insight, append it to that Insight rather than creating a
   near-duplicate.
5. Prioritize by impact. Negative end-user and developer feedback
   ranks highest, then explicit error-status spans, then evaluator
   regressions, then latency or cost outliers, then divergence from
   the agent's described intent. Issues that are more widespread and occur in many different sessions are higher impact than those that occur in one session.

## Method

1. Scope to the AUT through spans and fan out across sessions first.
   Intake traces cannot be filtered by agent — only spans carry the
   agent identity — so there is no agent-scoped trace tool. Spans can be
   filtered by ``agent_name``, so anchor your survey on spans scoped to
   **{agent}** (the span tools default to this agent). The AUT's work is
   organized into sessions (one ``session_id`` per end-to-end run), so
   begin with ``fetch_spans`` grouped by ``session_id`` (pass
   ``group_by="session_id"``) to recover the AUT's sessions in one shot and
   survey **many** of them — looking at 100 sessions is far more
   informative than 100 spans drawn from 2 sessions, especially in this
   initial exploration phase. Only pull a flat span list (``fetch_spans``
   without ``group_by``) once you have specific sessions worth opening up, and
   try to scope the spans you retrieve to the impactful ones.
2. Start with feedback: it is the strongest signal of a real problem.
   Pull negative end-user and developer feedback first, then fan out
   over the AUT's sessions with ``fetch_spans`` grouped by
   ``session_id``, looking for errors, outliers, and clusters of similar
   failures across as many sessions as you can.
3. Drill into the spans behind each candidate cluster: take the
   ``session_id`` (or ``trace_id``) of an interesting session and call
   ``fetch_spans`` with that filter (or ``get_span`` for one span) to
   find the actual LLM and tool calls where the root cause lives.
   Correlate feedback to its session via the session or trace id.
4. Check the existing Insights for the agent so you know which of your
   findings are new and which extend an Insight that already exists.

## Reporting your findings

When your analysis is complete, report everything in one final
``AnalystResult`` via ``return_result`` with your full change-set:

- ``new_insights``: Insights that do not already exist. Give each a
  short, human-readable title (a sentence naming the failure, e.g.
  'Retrieval drops relevant context near the token limit'), a
  description covering failure mode + affected component and
  the trace IDs as evidence.
- ``updated_insights``: new evidence — trace refs
  for Insights that already exist. Reference the target Insight by its
  ``id`` from the ``list_insights`` output (e.g.
  'insight-5Q2LoF8z8M9JZxZsHwJKNn'), not by its name. Appending evidence
  is the only change allowed on an existing Insight (you cannot rename,
  re-describe, or restatus it). Use this instead of re-filing a
  near-duplicate of an existing Insight.

### Evidence contract

Before filing, check each Insight against this list. An Insight that
cannot answer these is not ready, and filing it anyway is the fastest
way to lose the developer's trust:

1. **Failure mode** — what went wrong, in one sentence a developer can
   act on.
2. **Trigger** — the input, state, or condition under which it happens,
   and when it does not.
3. **Component** — the narrowest prompt, tool, retrieval step, model
   call, or harness behavior responsible.
4. **Evidence** — the ``trace_id`` values you actually read, not
   inferred. At least three distinct sessions before you file a pattern,
   so one unlucky run does not become a finding. Below that bar, report
   it in the summary as unconfirmed rather than filing it.
5. **Frequency** — how many distinct sessions show it, out of how many
   you surveyed. A pattern in 1 of 100 sessions is a different claim
   than one in 40 of 100, and the developer needs to know which.
6. **Impact** — the concrete cost: wrong answers, escalations, latency,
   spend, or a breached constraint. Tie this to the Ethos
   ``Trade-offs`` order.
7. **Falsifier** — what you would expect to see if this Insight were
   wrong. If you cannot name one, you are pattern-matching, not
   analyzing.

State uncertainty explicitly rather than rounding it away. "Three
sessions show this and I could not determine why" is a useful Insight;
a confident causal story built on three traces is not.

Producing the result ends the run, so gather all your evidence first
and emit one complete, well-evidenced change-set. If you found
nothing worth filing, return empty lists and say so in the summary.

Notes:
- Do not refer to the AUT agent as the AUT in the insights you create. The developer is not familiar with this vocabulary.
"""


ETHOS_HEADER = """
## Ethos

Use this as the contract for what the agent is supposed to do, what
success looks like, and what behavior should be flagged as divergence.
Flag agent divergence from the Ethos. The Ethos was authored by the
developer of the application and should be considered the purpose and goals.

Read these sections before you rank anything. They override your own
judgment about what matters, because they carry intent you cannot infer
from traces:

- **Constraints** are hard bounds the developer cannot cross — approved
  providers, data handling, compliance, production cost and latency
  ceilings. A trace showing the agent breaching one of these is the
  highest-severity finding available to you. Never file an Insight whose
  fix would require breaching one.
- **Trade-offs** tell you how to weigh competing findings: which
  qualities are hard gates, the priority order over the rest, and which
  regressions are unacceptable. Rank your Insights by this order rather
  than by a default of accuracy first. A cost or latency problem
  outranks an accuracy problem when the Ethos says it does.
- **Metric Semantics** defines what the agent's metric and telemetry
  field names actually mean. It wins over the conventional reading of a
  name. If a field is listed there, use only the claims it licenses; if
  a field's meaning is not established there or in the trace, say so and
  do not infer a meaning from the name. A field described there as broken
  or noisy is not evidence of anything — do not file against it.
- **Behavior** lists accepted limitations and known non-goals. Anything
  it names is by design, so do not file it as a defect.
- **Principles** says how the agent should decide when no rule covers
  the case. Behavior that follows a principle is correct even when it
  looks suboptimal in the trace: an agent that asks a clarifying
  question or refuses on principle is not failing. Check here before
  filing an Insight against a judgment call.
- **Vision** says where the agent is headed. Do not file an Insight
  against a capability it names as future work, and do not treat a gap
  it anticipates as a defect.

If a section is absent, fall back to your own judgment and say in the
summary which missing section would have sharpened the analysis. Do not
invent the developer's intent to fill the gap.

The Ethos does not tell you how to read evidence — that is your job, and
these defaults are yours, not the developer's. Weigh a breached
``Constraints`` bound first, then rank by the ``Trade-offs`` order, then
by frequency. An older Ethos may carry a ``Signals`` section from schema
version 1; treat anything in it as a hint, not as instruction.

Attribute every Insight to the narrowest component that could be
responsible — a prompt, a single tool, a retrieval step, the harness, or
the evaluator — rather than to the system as a whole. A fleet-wide model
or prompt change is not a valid recommendation for a failure localized to
one component.
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
        ethos: str | None = None,
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
        if ethos and ethos.strip():
            instructions = f"{instructions}\n{ETHOS_HEADER}\n\n{ethos.strip()}\n"
        self.context["analyst_instructions"] = instructions

    async def fetch_spans(
        self,
        filter: dict[str, object] | None = None,
        group_by: str | None = None,
        sort: str | None = None,
        mode: str = "detailed",
        limit: int | None = None,
    ) -> dict[str, object]:
        """List the AUT's spans from Intake, or roll them up into groups.

        One method, two modes:

        - **Grouped** (pass ``group_by``, e.g. ``group_by="session_id"``): rolls
          the matching spans up server-side into one row per group and returns
          ``{"groups": [...], "grouped_by": str, "count": int, "total": int,
          "truncated": bool}``, where each group is
          ``{"group": {<by-field>: value, ...}, "span_count": int}``. ``total`` is
          the server's full distinct-group count. **Start here** for initial
          exploration: grouping by ``session_id`` recovers the AUT's sessions
          so you fan out across **many** of them in one shot.
        - **Flat** (omit ``group_by``): returns the individual spans as
          ``{"spans": [...], "count": int, "truncated": bool}``. Use this once
          you have specific sessions worth opening up; scope it with a
          ``session_id`` or ``trace_id`` filter.

        In both modes ``truncated`` means more matched than ``limit``; narrow
        the filter or raise ``limit``.

        Args:
            filter: Raw Intake span filter pushed to the server. Supported keys:
                ``agent_name`` (e.g. "codex"), ``status`` ("success"/"error"/"cancelled"/"unknown"),
                ``kind`` ("LLM"/"TOOL"/"AGENT"/"CHAIN"/"EVALUATOR"/...),
                ``session_id``, ``trace_id``, ``parent_span_id`` (direct
                children of a span), ``model``, ``provider``, ``tool_name``,
                ``source``, ``project``, ``agent_id``, ``evaluation_id``,
                ``test_case_id``, and ``started_at`` (a range, e.g.
                ``{"gte": "2026-06-01T00:00:00"}``). Those are the only keys
                Intake serves. Every one takes a single exact value;
                ``started_at`` is the only key that takes a range, and no key
                accepts ``$in``. ``agent_name`` defaults
                to the run's agent under test when omitted; pass an explicit
                value to query another agent, or ``"__all__"`` to disable
                agent scoping. There is no span-id filter; use ``get_span``.
            group_by: When set, the span field(s) to group by. Only
                ``session_id`` and ``trace_id`` are groupable; pass one or both
                comma-separated. Omit for a flat span list.
            sort: Sort field. Defaults to ``"-started_at"`` for flat mode and
                ``"-span_count"`` for grouped mode.
            mode: ``"summary"`` omits input/output; ``"detailed"`` includes
                everything. Ignored in grouped mode.
            limit: Max rows to pull, clamped to the run's ceiling. Defaults to
                100 in grouped mode and 50 in flat mode.
        """
        return await spans.fetch_spans(
            self._deps,
            filter=filter,
            group_by=group_by,
            sort=sort,
            mode=mode,
            limit=limit,
        )

    async def get_span(self, span_id: str) -> dict[str, object]:
        """Fetch one Intake span by id.

        Args:
            span_id: Intake span id, such as one cited by an annotation.
        """
        return await spans.get_span(self._deps, span_id=span_id)

    async def fetch_scores(self, span_id: str) -> dict[str, object]:
        """Fetch evaluator results (scores) attached to a span.

        Evaluator results are verifier/judge outputs. Each has a ``name``, a
        numeric ``value`` and/or ``string_value``, and an optional ``comment``.
        For terminal-bench/eval traces the score lives on the EVALUATOR span.
        Returns ``{"evaluator_results": [...], "count": int}``.

        Args:
            span_id: Intake span id to read evaluator results for.
        """
        return await spans.fetch_scores(self._deps, span_id=span_id)

    async def fetch_annotations(
        self,
        filter: dict[str, object] | None = None,
        sort: str = "-created_at",
        limit: int = 50,
    ) -> dict[str, object]:
        """List span/session annotations (feedback, labels, notes), newest first.

        Returns ``{"annotations": [...], "count": int, "truncated": bool}``;
        ``truncated`` means more matched than ``limit``.

        Args:
            filter: Raw Intake annotation filter pushed to the server. Supported
                keys: ``kind`` ("feedback"/"label"/"note"/"metadata"),
                ``value_text`` (e.g. "negative" for feedback, or a label's text
                value), ``name`` (label name, e.g. "helpfulness"),
                ``value_numeric`` (a range object, e.g. ``{"lte": 2}`` for low
                scores), ``span_id``, ``session_id``, ``created_by``, and
                ``created_at`` (a range). To start with negative feedback use
                ``{"kind": "feedback", "value_text": "negative"}``. Omit to
                list all annotations.
            sort: Sort field; ``"-created_at"`` (default, newest first) or
                ``"created_at"``.
            limit: Max annotations to pull across pages, clamped to the ceiling.
        """
        return await annotations.fetch_annotations(self._deps, filter=filter, sort=sort, limit=limit)

    async def get_annotation(self, annotation_id: str) -> dict[str, object]:
        """Fetch one Intake annotation by id.

        Args:
            annotation_id: Intake annotation id.
        """
        return await annotations.get_annotation(self._deps, annotation_id=annotation_id)

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
    ethos: str | None = None,
    llm: UnifiedLLM | None = None,
    **kwargs: Any,
) -> Analyst:
    """Build the analyst with per-run scope and optional Nooa runtime overrides."""
    return Analyst(
        deps=deps,
        agent=agent,
        ethos=ethos,
        llm=llm,
        **kwargs,
    )
