# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted server-side Harbor evaluation runner."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from harbor.models.job.config import RetryConfig
from nemo_experimentalist_plugin.entities import (
    DatasetRef,
    EvaluationResult,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor_native import (
    HarborEvaluatorConfig,
    HarborNativeOutcomeEvaluator,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import EvaluationSubmission, RunProfile
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import candidate_agent_import


class HarborBridgeRunner:
    """Run one fixed trusted adapter over catalog-materialized tasks.

    ``agent_env`` is the complete host environment explicitly inherited by the
    bridge. Harbor scopes it to the installed-agent process; task and verifier
    containers continue to use the environment declared by their Harbor task.
    """

    def __init__(self, agent_env: Mapping[str, str]) -> None:
        self.agent_env = dict(agent_env)

    async def run(
        self,
        *,
        submission: EvaluationSubmission,
        profile: RunProfile,
        candidate_dir: Path,
        dataset_dir: Path,
        work_dir: Path,
    ) -> EvaluationResult:
        dataset = HarborDataset.from_ref(
            DatasetRef(
                uri=dataset_dir.resolve().as_uri(),
                metadata={
                    "id": submission.request_id,
                    "task_ids": [task.task_id for task in submission.envelope.tasks],
                },
            )
        )
        await dataset.validate()

        with candidate_agent_import(candidate_dir) as trusted_import_path:
            evaluator = HarborNativeOutcomeEvaluator(
                HarborEvaluatorConfig(
                    job_name=submission.request_id,
                    jobs_dir=Path("results"),
                    n_attempts=profile.attempts,
                    n_concurrent_trials=profile.concurrency,
                    retry=RetryConfig(max_retries=profile.retries),
                    quiet=True,
                    verifier_timeout_multiplier=profile.verifier_timeout_multiplier,
                    agent_timeout_multiplier=profile.agent_timeout_multiplier,
                    agent_setup_timeout_multiplier=profile.setup_timeout_multiplier,
                    environment_build_timeout_multiplier=profile.build_timeout_multiplier,
                    import_path=trusted_import_path,
                    scope_import_path=False,
                    agent_model_name=self.agent_env.get("AUT_MODEL_NAME"),
                    agent_env=self.agent_env,
                    trace_dir="/app/traces",
                ),
                experiment_dir=work_dir,
            )
            return await evaluator.run(candidate_dir, dataset)
