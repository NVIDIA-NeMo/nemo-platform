# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import AsyncGenerator

from nat.builder.builder import Builder  # type: ignore
from nat.builder.function import FunctionGroup  # type: ignore
from nat.cli.register_workflow import register_function_group  # type: ignore
from nat.data_models.function import FunctionGroupBaseConfig  # type: ignore
from pydantic import Field


class GovernedOptimizationToolsConfig(FunctionGroupBaseConfig, name="governed_optimization_tools"):
    """Deterministic tools for the governed optimization agent demo."""

    include: list[str] = Field(
        default_factory=lambda: [
            "search_internal_knowledge",
            "estimate_cost",
            "run_eval",
            "propose_update",
            "deploy_candidate",
        ],
        description="The optimization-governance tools to expose.",
    )


@register_function_group(config_type=GovernedOptimizationToolsConfig)
async def governed_optimization_tools(
    config: GovernedOptimizationToolsConfig,
    _builder: Builder,
) -> AsyncGenerator[FunctionGroup, None]:
    group = FunctionGroup(config=config)

    async def _search_internal_knowledge(source: str, query: str) -> str:
        """Search approved internal knowledge sources for agent optimization guidance."""
        return (
            f"Internal knowledge result from {source!r} for {query!r}: "
            "Use smaller local models for routine support questions, reserve larger hosted models for escalation, "
            "and ground answers in the onboarding KB before changing prompts."
        )

    async def _estimate_cost(model: str, monthly_requests: int) -> str:
        """Estimate monthly inference cost for a candidate agent configuration."""
        per_request = 0.002 if "nano" in model or "local" in model else 0.01
        estimated = monthly_requests * per_request
        return (
            f"Estimated monthly inference cost for {model!r} at {monthly_requests} requests/month: "
            f"${estimated:,.2f}. Recommendation: evaluate quality before switching traffic."
        )

    async def _run_eval(dataset: str, candidate: str) -> str:
        """Run an offline evaluation for a candidate prompt, model, or knowledge update."""
        return (
            f"Evaluation complete for candidate {candidate!r} on dataset {dataset!r}: "
            "answer quality +4.2%, hallucination rate -1.1%, estimated cost -18%."
        )

    async def _propose_update(target: str, change_summary: str) -> str:
        """Draft a knowledge-base or prompt update without publishing it."""
        return (
            f"Draft update for {target!r}: {change_summary}. "
            "Status: proposed only. A human owner should review before publishing."
        )

    async def _deploy_candidate(environment: str, candidate_id: str) -> str:
        """Deploy a candidate optimization to an environment."""
        return (
            f"DEPLOYED {candidate_id!r} to {environment!r}. "
            "If this appears in the guarded demo, the deploy guardrail failed."
        )

    selected = set(config.include)
    if "search_internal_knowledge" in selected:
        group.add_function(
            name="search_internal_knowledge",
            fn=_search_internal_knowledge,
            description=_search_internal_knowledge.__doc__,
        )
    if "estimate_cost" in selected:
        group.add_function(name="estimate_cost", fn=_estimate_cost, description=_estimate_cost.__doc__)
    if "run_eval" in selected:
        group.add_function(name="run_eval", fn=_run_eval, description=_run_eval.__doc__)
    if "propose_update" in selected:
        group.add_function(name="propose_update", fn=_propose_update, description=_propose_update.__doc__)
    if "deploy_candidate" in selected:
        group.add_function(name="deploy_candidate", fn=_deploy_candidate, description=_deploy_candidate.__doc__)

    yield group
