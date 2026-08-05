# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable optimizer Eval Author run orchestration."""

import importlib
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import unquote, urlparse

from nemo_eval_author_plugin.eval_author.inventory import (
    ReferenceTaskSetInventory,
    build_reference_task_set_inventory,
)
from nemo_eval_author_plugin.eval_author.models import EvalAuthorConfig, EvalAuthorRequest, EvalAuthorResult
from nemo_experimentalist_plugin.client import make_client
from nemo_experimentalist_plugin.entities import DatasetRef, Task, local_path_from_uri
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
        reference_inventory: ReferenceTaskSetInventory,
        *,
        client: AsyncNeMoPlatform,
    ) -> EvalAuthorResult: ...


async def run_eval_author(
    *,
    request: EvalAuthorRequest,
    experiment_dir: Path,
    workspace: str,
    base_url: str | None,
    config: EvalAuthorConfig,
    agent: Path | str | None = None,
    evaluator_type: EvaluatorType = "harbor",
) -> EvalAuthorResult:
    """Resolve one serializable request and run Eval Author.

    Args:
        request: Logical Insight plus split-agnostic evaluation-context references.
        experiment_dir: Working directory for Eval Author artifacts.
        workspace: Platform workspace.
        base_url: Platform base URL. ``None`` uses the active platform context.
        config: Eval Author tuning parameters.
        agent: Optional agent source override. When absent, the Insight's agent is used.
        evaluator_type: Evaluator adapter used to parse the task template.

    Returns:
        CLI-safe authored artifact descriptors, metric contract, and summary.

    The stale Experimentalist single-suite consumer intentionally has no compatibility
    overload here. Its later full-purge integration must consume this typed artifact
    boundary without restoring mutable train/validation result fields.
    """
    _enable_litellm_drop_params()

    experiment_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = experiment_dir.resolve()

    client = make_client(base_url)
    try:
        backend = make_experimentalist_backend(
            client=client,
            experiments_output=str(experiment_dir),
        )
        resolved_insight = await backend.get_insight(
            workspace=workspace,
            insight_id=_insight_locator(request, workspace=workspace),
        )
        agent_ref = agent if agent is not None else resolved_insight.agent
        agent_path = experiment_dir / "eval_author" / "source-agent"
        await backend.get_agent_code(workspace=workspace, agent=agent_ref, dest=agent_path)

        dataset_factory = DatasetFactory()
        staged_task_template = await stage_task_template(
            experiment_dir,
            request.evaluation_context.task_template,
            client=client,
            workspace=workspace,
        )
        staged_reference_task_sets = await _stage_reference_task_sets(
            experiment_dir,
            request.evaluation_context.reference_task_sets,
            client=client,
            workspace=workspace,
        )
        reference_inventory = build_reference_task_set_inventory(staged_reference_task_sets)
        eval_author = build_eval_author_agent(
            experiment_dir=experiment_dir,
            config=config,
        )
        return await eval_author.run(
            insight=resolved_insight,
            agent_path=agent_path,
            task_template=dataset_factory.build_task_template(evaluator_type, staged_task_template),
            reference_inventory=reference_inventory,
            client=client,
        )
    finally:
        await client.close()


def _insight_locator(request: EvalAuthorRequest, *, workspace: str) -> str:
    uri = request.insight.uri.strip()
    if not uri:
        raise ValueError("Eval Author request Insight URI must be non-empty")
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        return str(local_path_from_uri(uri, context="Eval Author Insight reference").resolve())
    if parsed.scheme == "insight":
        if parsed.netloc and parsed.netloc != workspace:
            raise ValueError(
                f"Insight reference workspace {parsed.netloc!r} does not match operational workspace {workspace!r}"
            )
        insight_id = unquote(parsed.path).strip("/")
        if not insight_id:
            raise ValueError(f"Insight reference has no id: {uri}")
        return insight_id
    if parsed.scheme:
        raise ValueError(f"Unsupported Eval Author Insight reference scheme {parsed.scheme!r}: {uri}")
    local_path = Path(uri).expanduser()
    return str(local_path.resolve()) if local_path.exists() else uri


async def _stage_reference_task_sets(
    experiment_dir: Path,
    references: Sequence[DatasetRef],
    *,
    client: AsyncNeMoPlatform,
    workspace: str,
) -> tuple[DatasetRef, ...]:
    staged: list[DatasetRef] = []
    staging_root = experiment_dir.resolve() / "dataset" / "reference-task-sets"
    for index, reference in enumerate(references, start=1):
        if urlparse(reference.uri).scheme != "fileset":
            staged.append(reference)
            continue
        destination = staging_root / f"{index:03d}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if not destination.is_dir():
                raise ValueError(f"Eval Author reference task-set staging path is not a directory: {destination}")
            shutil.rmtree(destination)
        try:
            await client.files.download(
                remote_path=reference.uri,
                local_path=str(destination),
                workspace=workspace,
            )
        except BaseException:
            if destination.exists():
                shutil.rmtree(destination)
            raise
        if not destination.is_dir() or not any(path.is_file() for path in destination.rglob("*")):
            if destination.exists():
                shutil.rmtree(destination)
            raise ValueError(f"Eval Author Fileset reference task set contains no files: {reference.uri}")
        staged.append(reference.model_copy(update={"uri": str(destination)}))
    return tuple(staged)


def build_eval_author_agent(
    *,
    experiment_dir: Path,
    config: EvalAuthorConfig,
    reporter: RunReporter | None = None,
) -> _EvalAuthorAgent:
    """Build the LLM-backed Eval Author agent lazily."""
    from nemo_eval_author_plugin.eval_author.agent import build_eval_author_agent as _build_eval_author_agent

    return _build_eval_author_agent(experiment_dir=experiment_dir, config=config, reporter=reporter)


def _enable_litellm_drop_params() -> None:
    """Let LiteLLM omit unsupported model parameters when it is installed."""
    try:
        litellm = cast(_LiteLLMModule, importlib.import_module("litellm"))
    except ModuleNotFoundError:
        return
    litellm.drop_params = True
