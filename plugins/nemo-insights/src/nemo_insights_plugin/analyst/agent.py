# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NeMo Insights analyst agent, built on Pydantic AI.

The analyst inspects recent traces from a target agent, identifies failure
patterns and performance regressions, and reports actionable Insights. It is a
Pydantic AI :class:`~pydantic_ai.Agent` with a fixed persona (``INSTRUCTIONS``)
and read-only tools for observability data.

Rather than mutating platform state mid-run through a series of write tools,
the analyst gathers evidence with its read tools and then emits a single
:class:`~nemo_insights_plugin.analyst.result.AnalystResult` as its typed
output. Producing that result ends the run and hands the entire change-set
(new insights and updates) back to the CLI, which is the only component
that persists.

The result is delivered via ``PromptedOutput`` rather than a tool call:
Anthropic rejects extended thinking and tool-based output in the same request,
and the analyst keeps adaptive thinking on for reasoning quality, so the
change-set is returned as a final structured message validated against the
``AnalystResult`` schema.

The analyst's persona, task, the agent-under-test name, and the optional AUT
spec are all formatted into the instructions by ``build_analyst_agent``; the
run is seeded with only the minimal ``KICKOFF`` user turn (the Anthropic
Messages API requires a non-empty ``messages`` array). The per-run config the
tools need is carried in :class:`~nemo_insights_plugin.analyst.deps.AnalystDeps`.
Workspace and base URL aren't in the instructions because the tools are already
scoped to them via ``AnalystDeps``.
"""

import os
from typing import Any

from nemo_insights_plugin.analyst.deps import AnalystDeps
from nemo_insights_plugin.analyst.functions.annotations import (
    fetch_annotations,
    get_annotation,
)
from nemo_insights_plugin.analyst.functions.insights import list_insights
from nemo_insights_plugin.analyst.functions.spans import (
    fetch_scores,
    fetch_spans,
    get_span,
)
from nemo_insights_plugin.analyst.observability import (
    ANALYST_OBSERVABILITY_AGENT_NAME,
    AnalystObservability,
)
from nemo_insights_plugin.analyst.result import AnalystResult
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai_harness import CodeMode

# The analyst runs on Claude Opus 4.8, but reached over the native Anthropic
# Messages wire format rather than Anthropic's own endpoint: NVIDIA's Inference
# Gateway (a LiteLLM proxy) exposes ``/v1/messages`` and authenticates with the
# gateway virtual key in ``INFERENCE_API_KEY``. The Anthropic SDK appends
# ``/v1/messages`` to the base URL, so we point it at the gateway root.
DEFAULT_MODEL = "aws/anthropic/bedrock-claude-opus-4-8"
INFERENCE_GATEWAY_BASE_URL = "https://inference-api.nvidia.com"
# Extended thinking effort. Opus 4.8 only accepts adaptive thinking with an
# ``output_config.effort`` level (it rejects the older fixed ``budget_tokens``
# form). We set these explicitly because the gateway-aliased model name hides
# the model identity from Pydantic AI's profile-based inference.
THINKING_EFFORT = "medium"
MAX_TOKENS = 16000

# Safety cap on model requests per run so a misbehaving loop cannot spin
# forever. Each tool-calling round is one request, so this bounds the analyst
# to roughly this many tool-use steps.
MAX_REQUESTS = 50

# ---------------------------------------------------------------------------
# Analyst persona + task + methodology, derived from docs/prd-por.md.
#
# This is the system prompt (Pydantic AI "instructions") and the only prompt
# the analyst gets — there is no separate user-message brief. ``{agent}`` is
# formatted in by ``build_analyst_agent`` and the optional AUT spec is appended
# as the final paragraph. Pydantic AI owns the tool catalog and JSON
# tool-calling protocol, so this text covers only the analyst's persona,
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

When your analysis is complete, report everything in one
final ``analyst_result`` with your full change-set:

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

Producing the result ends the run, so gather all your evidence first
and emit one complete, well-evidenced change-set. If you found
nothing worth filing, return empty lists and say so in the summary.

Notes:
- Do not refer to the AUT agent as the AUT in the insights you create. The developer is not familiar with this vocabulary.
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


def build_analyst_agent(
    agent: str,
    agent_spec: str | None = None,
    observability: AnalystObservability | None = None,
) -> Agent[AnalystDeps, AnalystResult]:
    """Build the analyst :class:`~pydantic_ai.Agent`.

    Args:
        agent: Name of the agent under test, formatted into the instructions.
        agent_spec: Optional spec describing the agent under test. When given,
            it is appended as the final paragraph of the instructions (under
            ``AGENT_SPEC_HEADER``) so the analyst can flag divergence from it.
        observability: Optional Pydantic AI OTel instrumentation for dogfooding
            analyst self-observability.
    """
    instructions = INSTRUCTIONS.format(agent=agent)
    if agent_spec and agent_spec.strip():
        instructions = f"{instructions}\n{AGENT_SPEC_HEADER}\n\n{agent_spec.strip()}\n"
    capabilities: list[Any] = [CodeMode()]
    if observability is not None:
        capabilities.append(Instrumentation(settings=observability.instrumentation_settings))
    return Agent(
        AnthropicModel(
            DEFAULT_MODEL,
            provider=AnthropicProvider(
                api_key=os.environ["INFERENCE_API_KEY"],
                base_url=INFERENCE_GATEWAY_BASE_URL,
            ),
        ),
        deps_type=AnalystDeps,
        name=ANALYST_OBSERVABILITY_AGENT_NAME,
        instructions=instructions,
        metadata=observability.metadata if observability else None,
        output_type=PromptedOutput(
            AnalystResult,
            name="analyst_result",
            description=(
                "The complete set of insights from this analysis. Emit this once, at the end; it ends the run."
            ),
        ),
        model_settings=AnthropicModelSettings(
            max_tokens=MAX_TOKENS,
            anthropic_thinking={"type": "adaptive"},
            anthropic_effort=THINKING_EFFORT,
        ),
        # Code mode (Pydantic AI Harness) collapses the analyst's read tools
        # into a single sandboxed ``run_code`` tool, so the model orchestrates
        # multi-step trace triage in one Python program instead of dozens of
        # serial tool-call round-trips.
        capabilities=capabilities,
        tools=[
            fetch_spans,
            get_span,
            fetch_scores,
            fetch_annotations,
            get_annotation,
            list_insights,
        ],
    )
