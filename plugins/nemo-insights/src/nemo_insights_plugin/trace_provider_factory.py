# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Construction and lifecycle management for Analyst trace providers."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import ClassVar

from langsmith import AsyncClient as AsyncLangSmithClient
from mlflow import MlflowClient
from mlflow.entities import Experiment
from nemo_platform_plugin.langsmith_trace_provider import LangSmithTraceProvider
from nemo_platform_plugin.mlflow_trace_provider import MLflowTraceProvider
from nemo_platform_plugin.trace_provider import TraceProvider


class TraceProviderConfigurationError(Exception):
    """A requested trace provider is missing required configuration."""


@dataclass(frozen=True)
class IntakeTraceConfig:
    """Use the Analyst's workspace-scoped default Intake provider."""

    name: ClassVar[str] = "intake"


@dataclass(frozen=True)
class LangSmithTraceConfig:
    """Read traces from one LangSmith project."""

    project: str
    name: ClassVar[str] = "langsmith"

    def __post_init__(self) -> None:
        if not self.project:
            raise ValueError("LangSmith project must not be empty")


@dataclass(frozen=True)
class MLflowTraceConfig:
    """Read traces from one MLflow experiment and tracking server."""

    experiment: str
    tracking_uri: str | None = None
    name: ClassVar[str] = "mlflow"

    def __post_init__(self) -> None:
        if not self.experiment:
            raise ValueError("MLflow experiment must not be empty")


type TraceProviderConfig = IntakeTraceConfig | LangSmithTraceConfig | MLflowTraceConfig


@asynccontextmanager
async def open_trace_provider(config: TraceProviderConfig) -> AsyncIterator[TraceProvider | None]:
    """Build one provider and keep its client alive for an Analyst run.

    ``None`` selects the Analyst's existing Intake default, whose Platform
    client is already owned by the run orchestrator.
    """
    if isinstance(config, IntakeTraceConfig):
        yield None
        return

    if isinstance(config, LangSmithTraceConfig):
        api_key = os.environ.get("LANGSMITH_API_KEY")
        if not api_key:
            raise TraceProviderConfigurationError("LANGSMITH_API_KEY is required for the LangSmith trace provider")
        async with AsyncLangSmithClient(
            api_url=os.environ.get("LANGSMITH_ENDPOINT"),
            api_key=api_key,
            workspace_id=os.environ.get("LANGSMITH_WORKSPACE_ID"),
        ) as client:
            project = await client.read_project(project_name=config.project)
            yield LangSmithTraceProvider(client, project_id=str(project.id))
        return

    client = MlflowClient(tracking_uri=config.tracking_uri)
    experiment = await asyncio.to_thread(_resolve_mlflow_experiment, client, config.experiment)
    yield MLflowTraceProvider(client, experiment_id=experiment.experiment_id)


def _resolve_mlflow_experiment(client: MlflowClient, name_or_id: str) -> Experiment:
    experiment = client.get_experiment_by_name(name_or_id)
    return experiment if experiment is not None else client.get_experiment(name_or_id)
