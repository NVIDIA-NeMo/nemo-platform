# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Managed host runtime helpers for Safe Synthesizer jobs."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

from nemo_safe_synthesizer_plugin.config import SafeSynthesizerConfig

TASK_MODULE = "nemo_safe_synthesizer_plugin.tasks.safe_synthesizer"
RUNTIME_BUILD_REQUIREMENTS = [
    "hatchling==1.26.3",
    "hatch-fancy-pypi-readme",
    "editables",
    "setuptools",
    "uv-dynamic-versioning",
]
FLASHINFER_CU129_INDEX_URL = "https://flashinfer.ai/whl/cu129"
PYTORCH_CU129_INDEX_URL = "https://download.pytorch.org/whl/cu129"
VLLM_CU129_VERSION = "0.20.0"


def vllm_cu129_wheel() -> str:
    """Return the direct vLLM CUDA 12.9 wheel URL for the current host."""
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        arch = "x86_64"
    elif machine in {"aarch64", "arm64"}:
        arch = "aarch64"
    else:
        raise RuntimeError(f"Unsupported architecture for vLLM CUDA 12.9 wheel: {platform.machine()}")

    wheel = f"vllm-{VLLM_CU129_VERSION}%2Bcu129-cp38-abi3-manylinux_2_31_{arch}.whl"
    return f"vllm @ https://github.com/vllm-project/vllm/releases/download/v{VLLM_CU129_VERSION}/{wheel}"


def runtime_package_index_options(runtime_package: str) -> list[str]:
    """Return package index options needed by the selected runtime package."""
    if "cu129" not in runtime_package:
        return []
    return [
        "--extra-index-url",
        FLASHINFER_CU129_INDEX_URL,
        "--extra-index-url",
        PYTORCH_CU129_INDEX_URL,
    ]


def runtime_package_extra_requirements(runtime_package: str) -> list[str]:
    """Return direct requirements needed by the selected runtime package."""
    if "cu129" not in runtime_package:
        return []
    return [vllm_cu129_wheel()]


def repo_root() -> Path:
    """Return the NeMo Platform repository root for this checkout."""
    return Path(__file__).resolve().parents[4]


def runtime_venv_path(config: SafeSynthesizerConfig) -> Path:
    """Return the configured runtime virtualenv path."""
    path = Path(config.runtime_venv).expanduser()
    if not path.is_absolute():
        path = repo_root() / path
    return path


def runtime_python_path(config: SafeSynthesizerConfig) -> Path:
    """Return the Python executable used for Safe Synthesizer task execution."""
    if config.runtime_python:
        path = Path(config.runtime_python).expanduser()
        if not path.is_absolute():
            path = repo_root() / path
        return path
    return runtime_venv_path(config) / "bin" / "python"


def runtime_task_command(config: SafeSynthesizerConfig, args: list[str] | None = None) -> list[str]:
    """Build the subprocess command for the Safe Synthesizer task module."""
    python = runtime_python_path(config)
    if not python.exists():
        raise RuntimeError(
            f"Safe Synthesizer runtime Python was not found at {python}. "
            "Run `nemo safe-synthesizer runtime setup` before starting local jobs."
        )
    return [str(python), "-m", TASK_MODULE, *(args or [])]


def setup_runtime(
    config: SafeSynthesizerConfig,
    *,
    force: bool = False,
    package: str | None = None,
    python_version: str | None = None,
) -> Path:
    """Create or update the separate Safe Synthesizer runtime virtualenv."""
    root = repo_root()
    venv_path = runtime_venv_path(config)
    if force and venv_path.exists():
        resolved_venv_path = venv_path.resolve()
        protected_paths = {Path("/"), Path.home(), root.resolve()}
        if resolved_venv_path in protected_paths:
            raise RuntimeError(f"Refusing to delete protected path: {resolved_venv_path}")
        shutil.rmtree(venv_path)

    python = python_version or config.runtime_python_version
    venv_command = ["uv", "venv", "--python", python, "--allow-existing", str(venv_path)]
    subprocess.run(venv_command, cwd=root, check=True)

    runtime_python = runtime_python_path(config)
    runtime_package = package or config.runtime_package
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(runtime_python),
            *RUNTIME_BUILD_REQUIREMENTS,
            "-e",
            str(root / "packages/nmp_build_tools"),
        ],
        cwd=root,
        check=True,
    )

    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(runtime_python),
            "--no-build-isolation",
            *runtime_package_index_options(runtime_package),
            "-e",
            str(root / "sdk/python/nemo-platform"),
            "-e",
            str(root / "packages/nmp_common"),
            "-e",
            str(root / "packages/nemo_platform_plugin"),
            "-e",
            str(root / "packages/nemo_platform"),
            *runtime_package_extra_requirements(runtime_package),
            runtime_package,
        ],
        cwd=root,
        check=True,
    )
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(runtime_python),
            "--no-build-isolation",
            "--no-deps",
            "-e",
            str(root / "plugins/nemo-safe-synthesizer"),
        ],
        cwd=root,
        check=True,
    )
    return runtime_python


def runtime_info(config: SafeSynthesizerConfig) -> dict[str, str | bool]:
    """Return lightweight status details for the configured runtime."""
    python = runtime_python_path(config)
    info: dict[str, str | bool] = {
        "venv": str(runtime_venv_path(config)),
        "python": str(python),
        "python_exists": python.exists(),
        "package": config.runtime_package,
    }
    if not python.exists():
        return info

    result = subprocess.run(
        [
            str(python),
            "-c",
            (
                "from importlib.metadata import version; "
                "print('nemo-safe-synthesizer=' + version('nemo-safe-synthesizer'))"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        info["installed"] = result.stdout.strip()
    else:
        info["installed"] = "unavailable"
        info["error"] = result.stderr.strip()
    return info
