# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bootstrap an isolated venv for the upstream AIPerf load generator.

`aiperf` (the PyPI package) pins ``aiofiles<24.2`` while NMP's
evaluator-service requires ``aiofiles>=25.1``. We can't add `aiperf` to the
workspace lockfile without downgrading the shared venv and breaking other
services, so the harness manages a dedicated, lock-free venv just for the
AIPerf binary.

The venv is created on first use (idempotent) and reused on subsequent runs.
The path is deterministic so local dev iterations are fast; in CI the cache is
discarded each run, which is acceptable since `aiperf` is a small install.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

log = logging.getLogger("nemo_guardrails_plugin.benchmarks.bootstrap")

# Versions pinned to what the upstream NeMo-Guardrails README installs alongside
# `python -m benchmark.aiperf`. We don't tighten further; aiperf's own metadata
# pins its dependencies.
_AIPERF_PACKAGES = ("aiperf", "huggingface_hub", "typer>=0.9", "httpx>=0.27")


class BootstrapError(RuntimeError):
    """Raised when we can't materialise the aiperf venv."""


def _venv_python(venv_dir: Path) -> Path:
    """Return the venv's python binary regardless of platform."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_bin(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts"
    return venv_dir / "bin"


def ensure_aiperf_venv(venv_dir: Path, *, force: bool = False) -> Path:
    """Ensure ``venv_dir`` contains a usable ``aiperf`` install.

    Returns the path to the venv's python interpreter so the caller can invoke
    ``<python> -m benchmark.aiperf`` with the right environment.
    """
    aiperf_bin = _venv_bin(venv_dir) / ("aiperf.exe" if os.name == "nt" else "aiperf")
    python_bin = _venv_python(venv_dir)

    if not force and aiperf_bin.exists() and python_bin.exists():
        log.info("Reusing existing aiperf venv at %s", venv_dir)
        return python_bin

    log.info("Creating aiperf venv at %s", venv_dir)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)

    # Prefer `uv venv` for speed and to match the rest of the project; fall
    # back to stdlib `venv` if `uv` isn't on PATH.
    try:
        subprocess.run(  # noqa: S603 - command is constructed internally
            ["uv", "venv", "--python", "3.11", str(venv_dir)],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError:
        log.warning("uv not found on PATH; falling back to `python -m venv`")
        subprocess.run(  # noqa: S603 - command is constructed internally
            [sys.executable, "-m", "venv", str(venv_dir)],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise BootstrapError(f"Failed to create aiperf venv at {venv_dir}: {e.stderr.decode(errors='replace')}") from e

    log.info("Installing %s into %s", ", ".join(_AIPERF_PACKAGES), venv_dir)
    try:
        # `uv pip install --python <venv-python>` is hermetic: it installs into
        # the target venv without touching the workspace lockfile.
        subprocess.run(  # noqa: S603 - command is constructed internally
            ["uv", "pip", "install", "--python", str(python_bin), *_AIPERF_PACKAGES],
            check=True,
        )
    except FileNotFoundError:
        log.warning("uv not found; falling back to `pip install`")
        subprocess.run(  # noqa: S603 - command is constructed internally
            [str(python_bin), "-m", "pip", "install", *_AIPERF_PACKAGES],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise BootstrapError(f"Failed to install aiperf into {venv_dir}: {e}") from e

    if not aiperf_bin.exists():
        raise BootstrapError(f"aiperf install completed but {aiperf_bin} is missing")

    return python_bin


def env_with_venv_on_path(venv_dir: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return a copy of ``base_env`` with the venv's bin dir prepended to PATH.

    The upstream `python -m benchmark.aiperf` wrapper shells out to a literal
    ``aiperf`` command, so the venv's bin dir has to come before whatever was
    on PATH inherited from the parent.
    """
    env = dict(base_env if base_env is not None else os.environ)
    venv_bin = str(_venv_bin(venv_dir))
    env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")
    return env
