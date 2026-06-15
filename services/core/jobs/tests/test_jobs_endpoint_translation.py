# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest
from fastapi import HTTPException
from nmp.core.jobs.api.v2.jobs.endpoints import validate_job_spec
from nmp.core.jobs.app.providers import SubprocessExecutionProvider
from nmp.core.jobs.app.schemas import PlatformJobSpec, PlatformJobStepSpec
from nmp.core.jobs.controllers.backends.docker import DockerJobExecutionProfile, DockerJobExecutionProfileConfig


def test_validate_job_spec_matches_provider_and_profile() -> None:
    spec = PlatformJobSpec(
        steps=[
            PlatformJobStepSpec(
                name="local-step",
                executor=SubprocessExecutionProvider(provider="cpu", profile="subprocess", command=["true"]),
            )
        ]
    )
    profiles = [
        DockerJobExecutionProfile(
            provider="cpu", profile="default", backend="docker", config=DockerJobExecutionProfileConfig()
        )
    ]

    with pytest.raises(HTTPException, match="cpu/subprocess"):
        validate_job_spec(spec, profiles)
