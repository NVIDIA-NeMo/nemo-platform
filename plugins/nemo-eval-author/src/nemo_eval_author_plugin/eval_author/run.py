# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable Eval Author run orchestration."""

import importlib
from pathlib import Path
from typing import Protocol, cast

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_experimentalist_plugin.client import make_client
from nemo_experimentalist_plugin.entities import DatasetRef, Task
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_task_template
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorType
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import DatasetFactory
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    make_experimentalist_backend,
)
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform


class _LiteLLMModule(Protocol):
    drop_params: bool


class _EvalAuthorAgent(Protocol):
    async def run(
        self,
        insight: Insight,
        agent_path: Path,
        task_template: Task,
        *,
        client: AsyncNeMoPlatform,
    ) -> EvalAuthorResult: ...


async def run_eval_author(
    *,
    insight: Path | str,
    task_template: DatasetRef,
    experiment_dir: Path,
    workspace: str,
    base_url: str | None,
    config: EvalAuthorConfig,
    agent: Path | str | None = None,
    evaluator_type: EvaluatorType = "harbor",
) -> EvalAuthorResult:
    """Resolve one Insight and task template, then run Eval Author.

    Args:
        insight: Local Insight path or platform Insight id.
        task_template: Local or Fileset-backed evaluator task template.
        experiment_dir: Working directory for authored artifacts.
        workspace: Platform workspace.
        base_url: Platform base URL. ``None`` uses the active platform context.
        config: Eval Author tuning parameters.
        agent: Optional agent source override. The Insight's agent is the default.
        evaluator_type: Evaluator adapter used to parse the task template.
    """
    _enable_litellm_drop_params()
    experiment_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = experiment_dir.resolve()
    insight_locator = str(insight.resolve()) if isinstance(insight, Path) else insight

    client = make_client(base_url)
    try:
        backend = make_experimentalist_backend(
            client=client,
            experiments_output=str(experiment_dir),
        )
        resolved_insight = await backend.get_insight(
            workspace=workspace,
            insight_id=insight_locator,
        )
        agent_ref = agent if agent is not None else resolved_insight.agent
        agent_path = experiment_dir / "eval_author" / "source-agent"
        await backend.get_agent_code(
            workspace=workspace,
            agent=agent_ref,
            dest=agent_path,
        )

        staged_template = await stage_task_template(
            experiment_dir,
            task_template,
            client=client,
            workspace=workspace,
        )
        parsed_template = DatasetFactory().build_task_template(
            evaluator_type,
            staged_template,
        )
        eval_author = build_eval_author_agent(
            experiment_dir=experiment_dir,
            config=config,
        )
        return await eval_author.run(
            insight=resolved_insight,
            agent_path=agent_path,
            task_template=parsed_template,
            client=client,
        )
    finally:
        await client.close()


def build_eval_author_agent(
    *,
    experiment_dir: Path,
    config: EvalAuthorConfig,
    reporter: RunReporter | None = None,
) -> _EvalAuthorAgent:
    """Build the LLM-backed Eval Author agent lazily."""
    from nemo_eval_author_plugin.eval_author.agent import build_eval_author_agent as _build_eval_author_agent

    return _build_eval_author_agent(
        experiment_dir=experiment_dir,
        config=config,
        reporter=reporter,
    )


def _enable_litellm_drop_params() -> None:
    """Let LiteLLM omit unsupported model parameters when it is installed."""
    try:
        litellm = cast(_LiteLLMModule, importlib.import_module("litellm"))
    except ModuleNotFoundError:
        return
    litellm.drop_params = True
