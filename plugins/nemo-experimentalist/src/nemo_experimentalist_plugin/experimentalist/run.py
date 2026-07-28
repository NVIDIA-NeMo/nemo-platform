# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reusable optimizer Experimentalist run orchestration."""

import importlib
from pathlib import Path
from typing import Literal, Protocol, cast

from nemo_experimentalist_plugin.experimentalist.agent import build_experimentalist_agent
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import DatasetRef
from nemo_experimentalist_plugin.experimentalist.components.loop import EvolutionaryOptimizerConfig
from nemo_experimentalist_plugin.experimentalist.deps import ExperimentalistDeps
from nemo_experimentalist_plugin.experimentalist.experimentalist_backend import (
    make_experimentalist_backend,
)
from nemo_platform import AsyncNeMoPlatform


class _LiteLLMModule(Protocol):
    drop_params: bool


async def run_experimentalist(
    *,
    agent: str | None = None,
    agent_spec: str | None = None,
    insight: Path | str | None,
    train_dataset: DatasetRef,
    validation_dataset: DatasetRef,
    experiment_dir: Path,
    workspace: str,
    client: AsyncNeMoPlatform | None,
    config: EvolutionaryOptimizerConfig,
    task_template: DatasetRef | None = None,
    mode: Literal["local", "remote"] = "local",
    framework_skills_dirs: list[Path] | None = None,
) -> str:
    """Build and run the Experimentalist against an agent and dataset.

    Args:
        agent: Optional baseline agent for Mode 2, or an override for the agent
            referenced by ``insight``. A local directory or a git ``url@ref``; a git
            source is fetched by the backend and enables opening a draft PR/MR for
            the winner against that ref.
        agent_spec: Optional URI of a markdown file describing the agent under test.
            Materialized by the backend and threaded to components that use it.
        insight: Optional Mode 1 insight — a local Insight file path or a platform
            insight id (fetched from the platform by the backend).
        train_dataset: Evaluator dataset reference for training.
        validation_dataset: Evaluator dataset reference for validation.
        task_template: Evaluator-specific task template used for production traces.
        experiment_dir: Working directory for optimization artifacts.
        workspace: Platform workspace.
        client: Optional caller-owned Platform client. Local-only Mode 2 runs
            may pass ``None``; Platform Insight access, mirroring, and Intake
            persistence require a client.
        config: Evolutionary optimizer configuration.
        mode: Backend mode. Local writes to ``experiment_dir``; remote uses the
            platform-backed backend.

    Returns:
        Terminal optimization summary.
    """
    # Logging is configured at the entry-point boundary (the root ``nemo`` CLI
    # callback runs ``configure_logging`` before dispatching this subcommand),
    # so this library function leaves root logging untouched.
    _enable_litellm_drop_params()

    experiment_dir.mkdir(parents=True, exist_ok=True)
    experiment_dir = experiment_dir.resolve()
    # Leave ``agent`` unresolved: it may be a git ``url@ref`` (not a filesystem path).
    # The backend's get_agent_code handles both local dirs and git sources.
    # A local file path is resolved; a platform insight id (str) is forwarded verbatim.
    insight = insight.resolve() if isinstance(insight, Path) else insight

    backend = make_experimentalist_backend(
        client=client,
        experiments_output=str(experiment_dir),
        mode=mode,
        storage=config.storage,
    )
    deps = ExperimentalistDeps(
        workspace=workspace,
        agent=agent,
        agent_spec=agent_spec,
        insight=insight,
        train_dataset=train_dataset,
        validation_dataset=validation_dataset,
        task_template=task_template,
        backend=backend,
        config=config,
    )
    experimentalist = build_experimentalist_agent(
        working_dir=experiment_dir,
        config=config,
        framework_skills_dirs=framework_skills_dirs,
    )
    result = await experimentalist.run(deps)
    return result.summary


def _enable_litellm_drop_params() -> None:
    """Let LiteLLM omit unsupported model parameters when it is installed."""
    try:
        litellm = cast(_LiteLLMModule, importlib.import_module("litellm"))
    except ModuleNotFoundError:
        return
    litellm.drop_params = True
