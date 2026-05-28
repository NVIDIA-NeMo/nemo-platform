# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
# property and proprietary rights in and to this material, related
# documentation and any modifications thereto. Any use, reproduction,
# disclosure or distribution of this material and related documentation
# without an express license agreement from NVIDIA CORPORATION or
# its affiliates is strictly prohibited.
"""Configuration for the Evaluator service."""

import logging
from pathlib import Path

from nmp.common.config import create_service_config_class, get_service_config
from pydantic import BaseModel, Field, model_validator

log = logging.getLogger(__name__)


class JobsConfig(BaseModel):
    configs_dir: str = Field(
        default="/configs", description="Directory path in job container for evaluation configuration."
    )
    volume_path: str = Field(
        default="/jobs",
        description="Directory path of the shared volume mount for job steps to persist artifacts for a job.",
    )
    results_dir: str = Field(
        default="/jobs/results", description="Directory path in the job container for results to be output."
    )
    dataset_dir: str = Field(
        default="/jobs/datasets",
        description="Directory path in the job container for dataset files to be downloaded to and loaded from.",
    )

    @model_validator(mode="after")
    def validate_directories(self):
        """Validate that all provider names are unique across types."""
        if not Path(self.results_dir).is_relative_to(Path(self.volume_path)):
            raise ValueError(
                f"job.results_dir {self.results_dir} is not a subpath of job.volume_path {self.volume_path}"
            )
        if not Path(self.dataset_dir).is_relative_to(Path(self.volume_path)):
            raise ValueError(
                f"job.dataset_dir {self.dataset_dir} is not a subpath of job.volume_path {self.volume_path}"
            )
        return self


class EvaluatorSettings(create_service_config_class("evaluator")):  # type: ignore[unsupported-base]
    """
    Configuration for the Evaluator service.

    Environment variables use the NMP_EVALUATOR_ prefix.
    """

    jobs: JobsConfig = Field(
        default_factory=JobsConfig, description="Configuration for jobs created with Evaluator service."
    )


settings = get_service_config(EvaluatorSettings)
