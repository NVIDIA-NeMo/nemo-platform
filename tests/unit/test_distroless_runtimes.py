# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Regression checks for Python runtime images that should stay distroless."""

from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_cpu_tasks_bake_defaults_to_distroless_runtime() -> None:
    bake = _read("docker-bake.hcl")

    assert 'variable "NMP_CPU_TASKS_RUNTIME_BASE" {\n  default = "root-distroless-base-3-13"\n}' in bake
    assert "NMP_CPU_TASKS_RUNTIME_BASE" in bake


def test_cpu_tasks_runtime_uses_distroless_compatible_stage() -> None:
    dockerfile = _read("docker/Dockerfile.nmp-cpu-tasks")

    assert "ARG NMP_CPU_TASKS_RUNTIME_BASE=nmp-python-base" in dockerfile
    assert "FROM ${NMP_CPU_TASKS_RUNTIME_BASE} AS runtime" in dockerfile
    assert "COPY --from=root-busybox /bin/sh /bin/sh" in dockerfile
    assert "COPY --from=root-busybox /bin/sed /bin/sed" in dockerfile
    assert "COPY --from=root-busybox /bin/tee /bin/tee" in dockerfile
    assert "COPY --from=root-busybox /bin/basename /bin/basename" in dockerfile
    assert "COPY --from=builder /bin/bash /bin/bash" in dockerfile
    assert "COPY --from=builder /bin/uv /bin/uv" in dockerfile
    assert "COPY --from=builder /usr/bin/env /usr/bin/env" in dockerfile
    assert "COPY --chown=1000:1000 --from=builder /app/.runtime-home/nvs /home/nvs" in dockerfile
    assert "RUN sh /bin/cve-cleanup.sh" not in dockerfile


def test_gym_tasks_builds_extensions_before_returning_to_cpu_runtime() -> None:
    dockerfile = _read("docker/Dockerfile.nmp-gym-tasks")

    assert "FROM ${NMP_CPU_TASKS_BASE} AS cpu-tasks" in dockerfile
    assert "FROM ${NMP_PYTHON_BASE} AS gym-builder" in dockerfile
    assert "FROM cpu-tasks AS runtime" in dockerfile
    assert 'ENV PATH="/opt/gym-venv/bin:/app/.venv/bin:$PATH"' in dockerfile
    assert 'PYTHONPATH=""' in dockerfile


def test_auditor_bake_defaults_to_distroless_runtime() -> None:
    bake = _read("docker-bake.hcl")

    assert 'variable "AUDITOR_RUNTIME_BASE" {\n  default = "root-distroless-base-3-13"\n}' in bake
    assert "AUDITOR_RUNTIME_BASE = AUDITOR_RUNTIME_BASE" in bake


def test_auditor_release_stage_has_no_runtime_package_manager_steps() -> None:
    dockerfile = _read("docker/Dockerfile.auditor-tasks")
    final_stage = dockerfile.split("FROM ${AUDITOR_RUNTIME_BASE} AS core-final", maxsplit=1)[1]

    assert "COPY --from=base /etc/passwd /etc/passwd" in final_stage
    assert "COPY --chown=1000:1000 --from=py-builder /app /app" in final_stage
    assert "\nRUN " not in final_stage


def test_jailbreak_detect_runtime_uses_distroless_stage() -> None:
    dockerfile = _read("services/jailbreak-detect/Dockerfile")

    assert "ARG DISTROLESS_BASE=nvcr.io/nvidia/distroless/python:3.11-v4.0.8" in dockerfile
    assert "FROM ${PYTHON_IMAGE} AS builder" in dockerfile
    assert "FROM ${DISTROLESS_BASE} AS runtime" in dockerfile
