# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the compile-side entry.

The plugin's local ``run`` does not invoke this code path — it lives
here so a future container submit drops in. We only check the
delegation contract: ``compile.platform_job_config_compiler`` forwards
to :mod:`nmp.unsloth.app.jobs.compiler` with the args the platform
schedule passes through.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from nmp.unsloth.compile import platform_job_config_compiler
from nmp.unsloth.schemas import (
    DatasetSpec,
    LoRAParams,
    ModelLoadSpec,
    OutputResponse,
    TrainingSpec,
    UnslothJobOutput,
)


def _canonical_spec() -> UnslothJobOutput:
    return UnslothJobOutput(
        model=ModelLoadSpec(name="default/base"),
        dataset=DatasetSpec(path="default/training"),
        training=TrainingSpec(lora=LoRAParams()),
        schedule={"max_steps": 1},  # type: ignore[arg-type]
        output=OutputResponse(
            name="r",
            type="adapter",
            save_method="lora",
            fileset="r",
        ),
    )


@pytest.mark.asyncio
async def test_compile_delegates_to_app_jobs_compiler() -> None:
    spec = _canonical_spec()
    sdk = object()

    sentinel = object()
    target = "nmp.unsloth.compile._compile_canonical"
    with patch(target, new=AsyncMock(return_value=sentinel)) as mock:
        result = await platform_job_config_compiler(
            workspace="default",
            spec=spec,
            sdk=sdk,  # type: ignore[arg-type]
            job_name="job-x",
            profile="gpu-large",
        )

    assert result is sentinel
    mock.assert_awaited_once_with(
        "default",
        spec,
        sdk,
        job_name="job-x",
        profile="gpu-large",
    )
