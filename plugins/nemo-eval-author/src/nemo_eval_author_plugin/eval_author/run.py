# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable optimizer Eval Author run orchestration."""

from pathlib import Path
from typing import Protocol

from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorResult
from nemo_experimentalist_plugin.client import make_client
from nemo_experimentalist_plugin.entities import Dataset, DatasetRef, Task
from nemo_experimentalist_plugin.experimentalist.components.dataset_staging import stage_task_template
from nemo_experimentalist_plugin.experimentalist.components.evaluator.base import EvaluatorType
from nemo_experimentalist_plugin.experimentalist.components.evaluator.factory import DatasetFactory
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    make_experimentalist_backend,
)
from nemo_experimentalist_plugin.experimentalist.reporting import RunReporter
from nemo_insights_plugin.entities import Insight
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.nooa_model_client import (
    ConfiguredModelClients,
    ConfiguredModelRefs,
    activate_model_clients,
    configured_model_refs,
    resolve_model_clients,
)


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
    model_refs: ConfiguredModelRefs | None = None,
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
        model_refs: Optional explicit default/fast Model Entity IDs. Unset uses
            the active Platform CLI context.

    Returns:
        Typed Eval Author output containing the train dataset, validation dataset, and summary.
    """
    selected_model_refs = model_refs if model_refs is not None else configured_model_refs()
    experiment_dir = experiment_dir.resolve()
    insight = insight.resolve() if isinstance(insight, Path) else insight

    client = make_client(base_url)
    model_clients: ConfiguredModelClients | None = None
    try:
        model_clients = await resolve_model_clients(client, selected_model_refs)
        experiment_dir.mkdir(parents=True, exist_ok=True)
        backend = make_experimentalist_backend(
            client=client,
            experiments_output=str(experiment_dir),
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
        with activate_model_clients(model_clients):
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
        try:
            if model_clients is not None:
                await model_clients.aclose()
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

    return _build_eval_author_agent(experiment_dir=experiment_dir, config=config, reporter=reporter)
