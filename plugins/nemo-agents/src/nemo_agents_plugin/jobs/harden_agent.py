# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""HardenAgentJob — the behavioral hardening loop.

Registered under ``nemo.jobs`` as ``agents.harden``. Attacks an agent via the
Auditor (garak), generates a managed NeMo Guardrails input-rail config for the
behavioral weaknesses, verifies it via the guardrail check surface, and records
each round to the experiments API. Behavioral surface only (see the Phase 1 plan
OQ1): the remediation is input/output rails, not tool-call blocking.

Two invocation paths share the same ``run(config)`` body: ``nemo agents harden
run`` (local, in-process) and ``nemo agents harden submit`` (dispatched).
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import ClassVar, Literal

from nemo_agents_plugin.jobs.evaluate_suite import _require_absolute
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.job_context import JobContext
from nemo_platform_plugin.jobs.api_factory import PlatformJobSpec
from nemo_platform_plugin.jobs.exceptions import PlatformJobCompilationError
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class HardenAgentConfig(BaseModel):
    probe_spec: str = Field(description="Comma-separated garak probe spec, e.g. 'promptinject,dan.DanInTheWild'.")
    judge_model: str = Field(description="Platform model id ('workspace/model') for the guardrail judge + defender.")
    mode: Literal["live", "replay"] = Field(default="replay", description="'replay' is the deterministic default.")
    replay_hitlog: str | None = Field(default=None, description="Absolute path to a saved garak hitlog (replay mode).")
    seed: int = Field(default=1234, description="garak seed for a deterministic live scan.")
    rounds: int = Field(default=3, ge=1)
    benign_csv: str | None = Field(default=None, description="Absolute path to the benign-suite CSV.")
    target_type: str = Field(default="nim", description="garak generator module for the agent-under-test (live mode).")
    target_model: str = Field(default="agent-under-test")
    aut_base_url: str = Field(default="http://127.0.0.1:8000/v1", description="Agent-under-test endpoint (live mode).")
    total_attempts: int = Field(default=8, ge=1)
    experiment_group: str = Field(default="agent-hardening")
    dataset_name: str = Field(default="hardening-probes")
    guardrail_config_name: str = Field(default="agent-hardening")
    workspace: str = Field(default="default")

    def validate_mode(self) -> None:
        """Replay mode needs a hitlog to replay; fail fast if it is missing."""
        if self.mode == "replay" and not self.replay_hitlog:
            raise ValueError("mode='replay' requires 'replay_hitlog' to point at a saved garak hitlog file.")


class HardenAgentJob(NemoJob):
    """Run the behavioral hardening loop end-to-end."""

    name: ClassVar[str] = "harden"
    description: ClassVar[str] = "Red-team an agent with garak and produce a verified NeMo Guardrails remediation."
    container: ClassVar[str] = "cpu-tasks"
    spec_schema: ClassVar[type[BaseModel]] = HardenAgentConfig

    @classmethod
    async def compile(  # type: ignore[override]
        cls,
        *,
        workspace: str,
        spec: HardenAgentConfig,
        entity_client: object,
        job_name: str | None,
        async_sdk: object,
        profile: str | None = None,
        options: dict | None = None,
    ) -> PlatformJobSpec:
        """Single-step PlatformJobSpec running ``nemo_agents_plugin.tasks.harden_agent``."""
        from nemo_platform_plugin.jobs.api_factory import (
            EnvironmentVariable,
            PlatformJobStep,
            SubprocessExecutionProviderSpec,
        )
        from nemo_platform_plugin.jobs.constants import (
            DEFAULT_JOB_STORAGE_PATH,
            PERSISTENT_JOB_STORAGE_PATH_ENVVAR,
        )

        # Subprocess work dir is not the caller's cwd; reject relative paths up front.
        _require_absolute(spec.replay_hitlog, "replay_hitlog")
        _require_absolute(spec.benign_csv, "benign_csv")

        # Mirror the run() guard so submit fails fast instead of spawning a doomed subprocess.
        if spec.mode == "replay" and not spec.replay_hitlog:
            raise PlatformJobCompilationError(
                "mode='replay' requires 'replay_hitlog' to point at a saved garak hitlog file."
            )

        spec_dict = spec.model_dump(mode="json")
        spec_dict["workspace"] = workspace

        environment: list[EnvironmentVariable] = [
            EnvironmentVariable(name=PERSISTENT_JOB_STORAGE_PATH_ENVVAR, value=DEFAULT_JOB_STORAGE_PATH),
        ]
        return PlatformJobSpec(
            steps=[
                PlatformJobStep(
                    name="harden",
                    executor=SubprocessExecutionProviderSpec(
                        provider="subprocess",
                        command=["python", "-m", "nemo_agents_plugin.tasks.harden_agent"],
                    ),
                    config=spec_dict,
                    environment=environment,
                ),
            ],
        )

    def run(self, config: dict, *, ctx: JobContext | None = None) -> dict:
        from nemo_platform import NeMoPlatform

        from nemo_agents_plugin.hardening import _wiring
        from nemo_agents_plugin.hardening.auditor_attack import AuditorAttacker
        from nemo_agents_plugin.hardening.loop import run_hardening_loop
        from nemo_agents_plugin.hardening.models import _serialize
        from nemo_agents_plugin.hardening.verify import load_benign_cases

        cfg = HardenAgentConfig.model_validate(config)
        cfg.validate_mode()

        platform = NeMoPlatform()  # sync client; auditor.run and inference resolve against the gateway
        group = platform.experiment_groups.create(workspace=cfg.workspace, name=cfg.experiment_group, exist_ok=True)

        attacker = AuditorAttacker(
            platform,
            probe_spec=cfg.probe_spec,
            seed=cfg.seed,
            target_type=cfg.target_type,
            target_model=cfg.target_model,
            target_options={cfg.target_type: {"uri": cfg.aut_base_url}},
            total_attempts=cfg.total_attempts,
            workspace=cfg.workspace,
        )
        benign_cases = load_benign_cases(Path(cfg.benign_csv)) if cfg.benign_csv else []

        state = asyncio.run(
            run_hardening_loop(
                attacker=attacker,
                complete=_wiring.build_completion_fn(platform, model=cfg.judge_model),
                apply_config=_wiring.build_apply_config(platform, workspace=cfg.workspace, name=cfg.guardrail_config_name),
                check=_wiring.build_check(
                    platform, workspace=cfg.workspace, config_name=cfg.guardrail_config_name, model=cfg.judge_model
                ),
                platform=platform,
                workspace=cfg.workspace,
                experiment_group_id=group.id,
                dataset_name=cfg.dataset_name,
                guardrail_config_name=cfg.guardrail_config_name,
                benign_cases=benign_cases,
                max_rounds=cfg.rounds,
                replay_hitlog=Path(cfg.replay_hitlog) if cfg.replay_hitlog else None,
            )
        )
        return _serialize(state)
