# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for evaluator metric-server image build helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from nemo_evaluator.shared.metric_bundles.container_image import (
    build_metric_server_image,
    metric_server_image_build_plan,
)


def test_build_metric_server_image_writes_self_contained_context() -> None:
    calls: list[list[str]] = []
    files: dict[str, str] = {}

    def runner(command: Sequence[str]) -> None:
        calls.append(list(command))
        context_dir = Path(command[-1])
        files["Dockerfile"] = (context_dir / "Dockerfile").read_text(encoding="utf-8")
        files["requirements.txt"] = (context_dir / "requirements.txt").read_text(encoding="utf-8")

    plan = build_metric_server_image(
        image="registry.test/evaluator-metric-server:dev",
        python_version="3.12",
        runner=runner,
    )

    assert plan.image == "registry.test/evaluator-metric-server:dev"
    assert plan.python_version == "3.12"
    assert plan.python_base_image == "python:3.12-slim"
    assert calls == [[*plan.command]]
    assert "FROM ${PYTHON_BASE_IMAGE}" in files["Dockerfile"]
    assert "python -m pip install" in files["Dockerfile"]
    assert "This is the evaluator metric-server base image" in files["Dockerfile"]
    assert "nemo-evaluator-sdk" not in files["requirements.txt"]
    assert "fastapi" not in files["requirements.txt"]
    assert "uvicorn" not in files["requirements.txt"]
    assert "cloudpickle" in files["requirements.txt"]


def test_metric_server_image_build_plan_accepts_base_image_override() -> None:
    plan = metric_server_image_build_plan(
        image="registry.test/evaluator-metric-server:alpine",
        python_version="3.12",
        python_base_image="python:3.12-alpine",
    )

    assert plan.python_base_image == "python:3.12-alpine"
    assert "PYTHON_BASE_IMAGE=python:3.12-alpine" in plan.command
