# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Trusted server-side Harbor evaluation runner."""

from __future__ import annotations

from pathlib import Path

from harbor.models.job.config import RetryConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    DatasetRef,
    EvaluationResult,
)
from nemo_experimentalist_plugin.harbor_bridge.contracts import EvaluationSubmission, RunProfile
from nemo_experimentalist_plugin.harbor_bridge.trusted_agent import candidate_agent_import
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr


class TrustedInferenceConfig(BaseModel):
    """Host-provided candidate inference configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    api_key: SecretStr
    api_base: AnyHttpUrl
    model_name: str = Field(min_length=1, max_length=256)


class HarborBridgeRunner:
    """Run one fixed trusted adapter over catalog-materialized tasks."""

    def __init__(self, inference: TrustedInferenceConfig) -> None:
        self.inference = inference

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
            evaluator = HarborEvaluator(
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
                    agent_model_name=self.inference.model_name,
                    agent_env={
                        "INFERENCE_API_KEY": self.inference.api_key.get_secret_value(),
                        "INFERENCE_API_BASE": str(self.inference.api_base),
                        "AUT_MODEL_NAME": self.inference.model_name,
                    },
                    trace_dir="/app/traces",
                ),
                experiment_dir=work_dir,
            )
            return await evaluator.run(candidate_dir, dataset)
