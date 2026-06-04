# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bootstrap an isolated venv for the upstream AIPerf load generator.

``aiperf`` pins ``aiofiles<24.2`` which conflicts with NMP's evaluator-service
requirement of ``aiofiles>=25.1``, so we install it into a dedicated venv
instead of the shared workspace one. The venv is reused across local runs;
CI gets a fresh one each invocation.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger("nemo_guardrails_plugin.benchmarks.bootstrap")

# Mirrors the upstream NeMo-Guardrails AIPerf README. We don't pin further;
# aiperf itself pins its transitives.
_AIPERF_PACKAGES = ("aiperf", "huggingface_hub", "typer>=0.9", "httpx>=0.27")


def ensure_aiperf_venv(venv_dir: Path) -> Path:
    """Idempotently create the aiperf venv. Returns the venv's python path.

    Uses ``uv venv`` + ``uv pip install`` since the harness is only ever invoked
    via ``make benchmark-guardrails``, which already requires ``uv`` to be on
    PATH. Skips both steps if the venv and the ``aiperf`` binary already exist.
    """
    python_bin = venv_dir / "bin" / "python"
    aiperf_bin = venv_dir / "bin" / "aiperf"

    if aiperf_bin.exists() and python_bin.exists():
        log.info("Reusing existing aiperf venv at %s", venv_dir)
        return python_bin

    log.info("Creating aiperf venv at %s", venv_dir)
    venv_dir.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # noqa: S603 - command is constructed internally
        ["uv", "venv", "--python", "3.11", str(venv_dir)],
        check=True,
        capture_output=True,
    )

    log.info("Installing %s into %s", ", ".join(_AIPERF_PACKAGES), venv_dir)
    subprocess.run(  # noqa: S603 - command is constructed internally
        ["uv", "pip", "install", "--python", str(python_bin), *_AIPERF_PACKAGES],
        check=True,
    )

    if not aiperf_bin.exists():
        raise RuntimeError(f"aiperf install completed but {aiperf_bin} is missing")
    return python_bin


def build_env(
    *,
    venv_bin_path: Path | str | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a child-process environment based on ``os.environ``.

    Optionally prepends ``venv_bin_path`` to ``PATH`` and overlays ``extra_env``.
    """
    env = dict(os.environ)
    if venv_bin_path:
        bin_path = str(venv_bin_path)
        env["PATH"] = f"{bin_path}{os.pathsep}{env.get('PATH', '')}"
    if extra_env:
        env.update(extra_env)
    return env
