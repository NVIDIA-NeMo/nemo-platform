# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable optimizer Eval Author run orchestration."""

import importlib
from pathlib import Path
from typing import Literal, Protocol, cast

from nemo_eval_author_plugin.backend import make_eval_author_backend
from nemo_eval_author_plugin.client import make_client
from nemo_eval_author_plugin.dataset_staging import stage_task_template
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_eval_author_plugin.evaluator import Dataset, Task
from nemo_eval_author_plugin.evaluator.base import EvaluatorType
from nemo_eval_author_plugin.evaluator.factory import DatasetFactory
from nemo_eval_author_plugin.evaluator.models import DatasetRef
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
        train_dataset: Dataset,
        validation_dataset: Dataset,
        *,
        client: AsyncNeMoPlatform,
    ) -> EvalAuthorResult: ...


async def run_eval_author(
    *,
    insight: Path | str,
    train_dataset: DatasetRef,
    validation_dataset: DatasetRef,
    task_template: DatasetRef,
    experiment_dir: Path,
    workspace: str,
    base_url: str | None,
    config: EvalAuthorConfig,
    agent: Path | str | None = None,
    evaluator_type: EvaluatorType = "harbor",
    mode: Literal["local", "remote"] = "local",
) -> EvalAuthorResult:
    """Build and run the Eval Author against an Insight and evaluator datasets.

    Args:
        insight: Local Insight file path or platform insight id.
        train_dataset: Evaluator dataset reference for training.
        validation_dataset: Evaluator dataset reference for validation.
        task_template: Local or Fileset-backed evaluator task template used for production traces.
        experiment_dir: Working directory for Eval Author artifacts.
        workspace: Platform workspace.
        base_url: Platform base URL. ``None`` uses the active platform context.
        config: Eval Author tuning parameters.
        agent: Optional agent source override. When absent, the Insight's agent is used.
        evaluator_type: Evaluator adapter used to parse datasets and task template.
        mode: Backend mode. Currently uses the same backend factory as Experimentalist.

    Returns:
        Typed Eval Author output containing the train dataset, validation dataset, and summary.
    """
    _enable_litellm_drop_params()

    experiment_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = experiment_dir.resolve()
    insight = insight.resolve() if isinstance(insight, Path) else insight

    client = make_client(base_url)
    try:
        backend = make_eval_author_backend(
            client=client,
            experiments_output=str(experiment_dir),
            mode=mode,
        )
        resolved_insight = await backend.get_insight(workspace=workspace, insight_id=str(insight))
        agent_ref = agent if agent is not None else resolved_insight.agent
        agent_path = experiment_dir / "eval_author" / "source-agent"
        await backend.get_agent_code(workspace=workspace, agent=agent_ref, dest=agent_path)

        dataset_factory = DatasetFactory()
        staged_task_template = await stage_task_template(
            experiment_dir,
            task_template,
            client=client,
            workspace=workspace,
        )
        eval_author = build_eval_author_agent(
            experiment_dir=experiment_dir,
            config=config,
        )
        return await eval_author.run(
            insight=resolved_insight,
            agent_path=agent_path,
            task_template=dataset_factory.build_task_template(evaluator_type, staged_task_template),
            train_dataset=dataset_factory.build_dataset(evaluator_type, train_dataset),
            validation_dataset=dataset_factory.build_dataset(evaluator_type, validation_dataset),
            client=client,
        )
    finally:
        await client.close()


def build_eval_author_agent(*, experiment_dir: Path, config: EvalAuthorConfig) -> _EvalAuthorAgent:
    """Build the LLM-backed Eval Author agent lazily."""
    from nemo_eval_author_plugin.eval_author.agent import build_eval_author_agent as _build_eval_author_agent

    return _build_eval_author_agent(experiment_dir=experiment_dir, config=config)


def _enable_litellm_drop_params() -> None:
    """Let LiteLLM omit unsupported model parameters when it is installed."""
    try:
        litellm = cast(_LiteLLMModule, importlib.import_module("litellm"))
    except ModuleNotFoundError:
        return
    litellm.drop_params = True
