# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NAT workflow backend as an AgentAttemptRuntime."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunConfig, AgentEvalTask

from runtimes.shared.artifacts import build_agent_eval_attempt
from runtimes.shared.config import WorkflowRuntimeConfig
from runtimes.shared.constants import INSTRUCTION_CONTAINER_PATH, WORKFLOW_CONTAINER_PATH
from runtimes.shared.container_env import base_container_env
from runtimes.shared.environment import (
    AgentEnvironmentProvider,
    DockerEnvironmentProvider,
    EnvRunSpec,
)
from runtimes.shared.layout import AgenticRunLayout, resolve_run_layout
from runtimes.shared.task_loader import task_agent_timeout_sec
from runtimes.shared.verify import apply_verify_to_metadata, maybe_run_verify
from runtimes.workflow.command import build_workflow_agent_cmd
from runtimes.workflow.prep import prepare_workflow_for_runtime

RUNTIME_NAME = "workflow"


class NatWorkflowAttemptRuntime:
    """Run agentic-use tasks via task-local ``nat run`` workflows."""

    def __init__(
        self,
        config: WorkflowRuntimeConfig,
        *,
        environment: AgentEnvironmentProvider | None = None,
    ) -> None:
        self.config = config
        self.environment = environment or DockerEnvironmentProvider()

    async def run_tasks(
        self,
        tasks: Sequence[AgentEvalTask],
        config: AgentEvalRunConfig | None = None,
    ) -> list[AgentEvalAttempt]:
        attempts: list[AgentEvalAttempt] = []
        for task in tasks:
            layout = resolve_run_layout(task, self.config.shared, config)
            shared = self.config.shared
            handle = await self.environment.prepare(task, config)
            try:
                result = await handle.run_agent(self._agent_run_spec(task, layout))
                verify_outcome = await maybe_run_verify(
                    handle,
                    enabled=shared.run_verify and result.ok,
                    task_dir=Path(str(task.metadata["task_dir"])),
                    layout=layout,
                    nmp_base_url=shared.nmp_base_url,
                    agent_backend=RUNTIME_NAME,
                    agent_model=self._resolved_model(),
                    smoke_workspace=shared.smoke_workspace,
                    timeout_sec=shared.timeout_sec + 120,
                    extra_args=list(shared.docker_extra_args),
                )
            finally:
                await handle.close()

            attempt = build_agent_eval_attempt(
                task=task,
                layout=layout,
                runtime_name=RUNTIME_NAME,
                agent_model=self._resolved_model(),
                exit_code=result.exit_code,
                agent_ok=result.ok,
            )
            apply_verify_to_metadata(attempt.metadata, verify_outcome)
            attempts.append(attempt)
        return attempts

    def _resolved_model(self) -> str:
        return self.config.agent_model or "unknown"

    def _agent_run_spec(self, task: AgentEvalTask, layout: AgenticRunLayout) -> EnvRunSpec:
        task_dir = Path(str(task.metadata["task_dir"]))
        workflow_path = task_dir / "workflow.yml"
        if not workflow_path.exists():
            raise FileNotFoundError(f"workflow.yml not found in {task_dir}")

        shared = self.config.shared
        task_timeout = task_agent_timeout_sec(task_dir)
        timeout_sec = max(shared.timeout_sec, task_timeout or 0)

        workflow_host = prepare_workflow_for_runtime(
            workflow_path,
            layout.agent_log_dir,
            shared.nmp_base_url,
            nat_model=self.config.agent_model,
        )

        env = base_container_env(shared, timeout_sec=timeout_sec)
        if shared.nvidia_api_key:
            env["NVIDIA_API_KEY"] = shared.nvidia_api_key
        if self.config.agent_model:
            env["NAT_MODEL"] = self.config.agent_model

        mounts = [
            (str(layout.instruction_path), INSTRUCTION_CONTAINER_PATH),
            (str(layout.agent_log_dir), "/logs/agent"),
            (str(layout.workspace_dir), "/app/workspace"),
            (str(workflow_host), WORKFLOW_CONTAINER_PATH),
            (str(layout.state_dir), "/data"),
        ]

        return EnvRunSpec(
            command=build_workflow_agent_cmd(WORKFLOW_CONTAINER_PATH, INSTRUCTION_CONTAINER_PATH),
            env=env,
            mounts=mounts,
            timeout=timeout_sec + 120,
            extra_args=list(shared.docker_extra_args),
        )
