# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build helpers for evaluator metric-server base images."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Sequence
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from nmp.common.jobs.image import get_qualified_image
from pydantic import BaseModel, ConfigDict, Field

CommandRunner = Callable[[Sequence[str]], None]


class MetricServerImageBuildPlan(BaseModel):
    """Resolved Docker build plan for the metric-server base image."""

    model_config = ConfigDict(extra="forbid")

    image: str
    python_version: str
    python_base_image: str
    command: list[str] = Field(min_length=1)


def default_metric_server_python_version() -> str:
    """Return the current interpreter's major.minor version."""
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def metric_server_image_name(python_version: str) -> str:
    """Return the platform image name for a metric-server Python version."""
    return f"nemo-evaluator-metric-server-py{python_version.replace('.', '')}"


def default_python_base_image(python_version: str | None = None) -> str:
    """Return the default Python base image for metric-server images."""
    effective_python_version = python_version or default_metric_server_python_version()
    return f"python:{effective_python_version}-slim"


def default_metric_server_image(python_version: str | None = None) -> str:
    """Return the configured platform image reference for the metric server."""
    effective_python_version = python_version or default_metric_server_python_version()
    return get_qualified_image(metric_server_image_name(effective_python_version))


def metric_server_image_build_plan(
    *,
    image: str | None = None,
    python_version: str | None = None,
    python_base_image: str | None = None,
    docker_executable: str = "docker",
) -> MetricServerImageBuildPlan:
    """Resolve the Docker build plan without executing it."""
    effective_python_version = python_version or default_metric_server_python_version()
    effective_python_base_image = python_base_image or default_python_base_image(effective_python_version)
    effective_image = image or default_metric_server_image(effective_python_version)
    return MetricServerImageBuildPlan(
        image=effective_image,
        python_version=effective_python_version,
        python_base_image=effective_python_base_image,
        command=[
            docker_executable,
            "build",
            "--build-arg",
            f"PYTHON_BASE_IMAGE={effective_python_base_image}",
            "-t",
            effective_image,
        ],
    )


def build_metric_server_image(
    *,
    image: str | None = None,
    python_version: str | None = None,
    python_base_image: str | None = None,
    docker_executable: str = "docker",
    runner: CommandRunner | None = None,
) -> MetricServerImageBuildPlan:
    """Build the evaluator metric-server base image."""
    plan = metric_server_image_build_plan(
        image=image,
        python_version=python_version,
        python_base_image=python_base_image,
        docker_executable=docker_executable,
    )
    with TemporaryDirectory(prefix="nemo-evaluator-metric-server-image-") as temp_dir:
        context_dir = Path(temp_dir)
        _write_build_context(context_dir)
        command = [*plan.command, str(context_dir)]
        if runner is None:
            subprocess.run(command, check=True)
        else:
            runner(command)
    return plan.model_copy(update={"command": command})


def _write_build_context(context_dir: Path) -> None:
    (context_dir / "Dockerfile").write_text(_dockerfile_source(), encoding="utf-8")
    (context_dir / "requirements.txt").write_text(_requirements_source(), encoding="utf-8")


def _dockerfile_source() -> str:
    template = files("nemo_evaluator.shared.metric_bundles").joinpath("templates", "Dockerfile.metric-server-base")
    return template.read_text(encoding="utf-8")


def _requirements_source() -> str:
    template = files("nemo_evaluator.shared.metric_bundles").joinpath(
        "templates", "requirements.metric-server-base.txt"
    )
    return template.read_text(encoding="utf-8")
