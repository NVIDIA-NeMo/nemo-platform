# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""AUT (agent-under-test) backend as an AgentAttemptRuntime."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nemo_evaluator_sdk.agent_eval.runtimes.environment import AgentEnvironmentProvider, EnvRunSpec
from nemo_evaluator_sdk.agent_eval.runtimes.verify import apply_verify_to_metadata
from nemo_evaluator_sdk.agent_eval.types import AgentEvalAttempt, AgentEvalRunConfig, AgentEvalTask

from runtimes.aut.command import build_aut_agent_cmd
from runtimes.aut.prep import prepare_aut_config_for_runtime
from runtimes.shared.config import AutRuntimeConfig
from runtimes.shared.constants import (
    DOCKER_SOCKET_CONTAINER_PATH,
    DOCKER_SOCKET_HOST_PATH,
    INSTRUCTION_CONTAINER_PATH,
    REPO_ROOT,
)
from runtimes.shared.platform import (
    AgenticRunLayout,
    DockerEnvironmentProvider,
    agent_log_has_workflow_error,
    base_container_env,
    build_agent_eval_attempt,
    maybe_run_verify,
    resolve_run_layout,
    task_agent_timeout_sec,
)

RUNTIME_NAME = "aut"
AUT_CONFIG_CONTAINER_PATH = "/tmp/aut_agent.yml"


class AutAgentAttemptRuntime:
    """Run agentic-use tasks via a deployed platform agent-under-test."""

    def __init__(
        self,
        config: AutRuntimeConfig,
        *,
        environment: AgentEnvironmentProvider | None = None,
    ) -> None:
        if not config.aut_agent_name:
            raise ValueError("AutAgentAttemptRuntime requires aut_agent_name")
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

                agent_ok = result.ok
                log_path = layout.agent_log_dir / "nat_agent.log"
                log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
                if agent_ok and log_text and agent_log_has_workflow_error(log_text):
                    agent_ok = False

                verify_outcome = await maybe_run_verify(
                    handle,
                    enabled=shared.run_verify and agent_ok,
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
                agent_ok=agent_ok,
                run_id=config.run_id if config is not None else None,
            )
            apply_verify_to_metadata(attempt.metadata, verify_outcome)
            attempts.append(attempt)
        return attempts

    def _resolved_model(self) -> str:
        return self.config.agent_model or "unknown"

    def _agent_run_spec(self, task: AgentEvalTask, layout: AgenticRunLayout) -> EnvRunSpec:
        task_dir = Path(str(task.metadata["task_dir"]))
        shared = self.config.shared
        task_timeout = task_agent_timeout_sec(task_dir)
        timeout_sec = max(shared.timeout_sec, task_timeout or 0)

        env = base_container_env(shared, timeout_sec=timeout_sec)
        if shared.nvidia_api_key:
            env["NVIDIA_API_KEY"] = shared.nvidia_api_key
        if self.config.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = self.config.anthropic_api_key
        if self.config.aut_seed_providers and self.config.inference_nvidia_api_key:
            env["INFERENCE_NVIDIA_API_KEY"] = self.config.inference_nvidia_api_key
        if self.config.agent_model:
            env["NAT_MODEL"] = self.config.agent_model

        env["AUT_AGENT_NAME"] = self.config.aut_agent_name
        env["AUT_SEED_PROVIDERS"] = "1" if self.config.aut_seed_providers else "0"
        env["AUT_HEALTH_WAIT_SECONDS"] = str(self.config.aut_health_wait_seconds)

        aut_config_host: Path | None = None
        if self.config.aut_agent_config is not None:
            aut_config_path = Path(self.config.aut_agent_config)
            if not aut_config_path.is_absolute():
                aut_config_path = (REPO_ROOT / aut_config_path).resolve()
            if not aut_config_path.exists():
                raise FileNotFoundError(f"AUT config not found: {aut_config_path}")
            aut_config_host = prepare_aut_config_for_runtime(
                aut_config_path,
                layout.agent_log_dir,
                nat_model=self.config.agent_model,
                nmp_base_url=shared.nmp_base_url,
            )
            env["AUT_AGENT_CONFIG"] = AUT_CONFIG_CONTAINER_PATH
        else:
            env["AUT_AGENT_CONFIG"] = ""

        mounts = [
            (str(layout.instruction_path), INSTRUCTION_CONTAINER_PATH),
            (str(layout.agent_log_dir), "/logs/agent"),
            (str(layout.workspace_dir), "/app/workspace"),
            (str(layout.state_dir), "/data"),
        ]
        if aut_config_host is not None:
            mounts.append((str(aut_config_host), AUT_CONFIG_CONTAINER_PATH))
        if DOCKER_SOCKET_HOST_PATH.exists():
            mounts.append((str(DOCKER_SOCKET_HOST_PATH), DOCKER_SOCKET_CONTAINER_PATH))

        return EnvRunSpec(
            command=build_aut_agent_cmd(INSTRUCTION_CONTAINER_PATH),
            env=env,
            mounts=mounts,
            timeout=timeout_sec + 120,
            extra_args=list(shared.docker_extra_args),
        )
