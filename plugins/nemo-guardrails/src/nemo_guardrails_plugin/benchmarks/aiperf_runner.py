# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Invoke the upstream NeMo Guardrails AIPerf sweep runner as a subprocess.

The upstream code lives in ``${NEMO_GUARDRAILS_REPO_ROOT}/benchmark/`` and is not
installed as a package; we set ``PYTHONPATH`` so ``python -m benchmark.aiperf``
resolves.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from nemo_guardrails_plugin.benchmarks.bootstrap import build_env

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SweepRunResult:
    """Outcome of a single ``aiperf profile`` invocation (one concurrency level)."""

    # Name of the per-sweep subdirectory AIPerf created, e.g. ``"concurrency16"``.
    # Surfaced in the harness's summary log so failures point at a directory name.
    sweep_label: str
    # Absolute path to the sweep's output directory under
    # ``aiperf_results/<batch>/<timestamp>/<sweep_label>/``. Contains the AIPerf
    # CSV, per-request JSONL, run metadata, and the wrapper's process_result.json.
    output_dir: Path
    # Exit code of the AIPerf subprocess for this sweep (0 = success). Sourced from
    # ``process_result.json``; defaults to 1 if that file is missing or unparseable
    # so a crashed subprocess does not silently pass.
    return_code: int
    # Wall-clock duration of the sweep in seconds, read from ``run_metadata.json``.
    # 0.0 when AIPerf never wrote metadata (typically because it crashed early).
    duration_seconds: float
    # Path to ``run_metadata.json`` if AIPerf wrote it, else ``None``. Kept on the
    # result for downstream analyzers that want to inspect AIPerf's view of the run.
    metadata_path: Path | None
    # Path to ``process_result.json`` if AIPerf wrote it, else ``None``. This is
    # the upstream wrapper's record of the subprocess exit; useful when
    # ``return_code`` itself looks suspicious.
    process_result_path: Path | None

    @property
    def passed(self) -> bool:
        return self.return_code == 0


def prepare_runtime_aiperf_config(
    *,
    template_path: Path,
    runtime_config_path: Path,
    aiperf_output_dir: Path,
) -> dict[str, Any]:
    """Materialize the AIPerf config this run will use.

    Reads the checked-in ``template_path`` config, overrides its
    ``output_base_dir`` to point inside the current run's directory, and writes
    the result to ``runtime_config_path``. AIPerf is later invoked with
    ``--config-file <runtime_config_path>`` so every artifact lands under a
    separate per-run directory.

    Returns the parsed config dict so callers can log fields (sweep params,
    benchmark_duration) without re-reading the file.
    """
    if not template_path.is_file():
        raise FileNotFoundError(f"AIPerf template not found: {template_path}")

    config = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"Expected a YAML mapping at {template_path}, got {type(config).__name__}")

    # Point AIPerf's output_base_dir at this run's directory so its results
    # nest under our per-run artifacts tree.
    config["output_base_dir"] = str(aiperf_output_dir)
    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    return config


def run_aiperf_sweep(
    *,
    nemoguardrails_repo_root: Path,
    runtime_config: Path,
    log_path: Path,
    python_executable: str | None = None,
    venv_bin_path: Path | str | None = None,
    extra_env: dict[str, str] | None = None,
) -> int:
    """Run ``python -m benchmark.aiperf --config-file ...`` and tee output.

    Returns the subprocess exit code. The caller decides whether to treat a
    non-zero code as a sweep-level failure or as a fail-fast.

    ``python_executable`` should point at the python in the dedicated aiperf
    venv (see :mod:`nemo_guardrails_plugin.benchmarks.bootstrap`). ``venv_bin_path``
    prepends that venv's ``bin/`` to ``PATH`` so the ``aiperf`` CLI is resolvable
    when the wrapper shells out to it.

    Note: AIPerf's built-in pre-flight check does a GET on
    ``urljoin(config.base_config.url, "/v1/models")`` with no override
    available upstream yet. The harness runs a tiny shim that satisfies this
    probe; see :mod:`nemo_guardrails_plugin.benchmarks.shim`.
    """
    python_bin = python_executable or sys.executable
    # Upstream `benchmark.aiperf` is a single-command Typer app; invoking
    # `python -m benchmark.aiperf --config-file ...` runs the only command.
    # Passing a literal `run` subcommand confuses Typer.
    cmd = [
        python_bin,
        "-m",
        "benchmark.aiperf",
        "--config-file",
        str(runtime_config),
    ]

    env = build_env(
        venv_bin_path=venv_bin_path,
        extra_env={
            "PYTHONPATH": str(nemoguardrails_repo_root),
            **(extra_env or {}),
        },
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    log.info("Running aiperf sweep: %s (cwd=%s)", " ".join(cmd), nemoguardrails_repo_root)

    with log_path.open("wb") as log_fh:
        proc = subprocess.run(  # noqa: S603 - command is constructed internally
            cmd,
            cwd=str(nemoguardrails_repo_root),
            env=env,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            check=False,
        )

    return proc.returncode


def collect_sweep_results(aiperf_output_dir: Path) -> list[SweepRunResult]:
    """Walk the AIPerf output tree and surface per-sweep exit status.

    Layout:
    ``<aiperf_output_dir>/<batch>/<timestamp>/<sweep-label>/{run_metadata.json,process_result.json}``

    Missing ``process_result.json`` is treated as a failure for that sweep so a
    crashed AIPerf subprocess does not silently pass.
    """
    if not aiperf_output_dir.is_dir():
        return []

    results: list[SweepRunResult] = []
    for batch_dir in sorted(p for p in aiperf_output_dir.iterdir() if p.is_dir()):
        for timestamp_dir in sorted(p for p in batch_dir.iterdir() if p.is_dir()):
            for sweep_dir in sorted(p for p in timestamp_dir.iterdir() if p.is_dir()):
                results.append(_load_sweep_result(sweep_dir))
    return results


def _load_sweep_result(sweep_dir: Path) -> SweepRunResult:
    """Load the sweep result from the given directory.

    Layout:
    ``<aiperf_output_dir>/<batch>/<timestamp>/<sweep-label>/{run_metadata.json,process_result.json}``
    """
    metadata_path = sweep_dir / "run_metadata.json"
    process_result_path = sweep_dir / "process_result.json"

    return_code = 1
    duration = 0.0

    if process_result_path.is_file():
        try:
            data = json.loads(process_result_path.read_text(encoding="utf-8"))
            return_code = int(data.get("returncode", 1))
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            log.warning("Could not parse %s: %s", process_result_path, exc)

    if metadata_path.is_file():
        try:
            md = json.loads(metadata_path.read_text(encoding="utf-8"))
            duration = float(md.get("duration_seconds", 0.0) or 0.0)
        except (json.JSONDecodeError, OSError, ValueError, TypeError) as exc:
            log.warning("Could not parse %s: %s", metadata_path, exc)

    return SweepRunResult(
        sweep_label=sweep_dir.name,
        output_dir=sweep_dir,
        return_code=return_code,
        duration_seconds=duration,
        metadata_path=metadata_path if metadata_path.is_file() else None,
        process_result_path=process_result_path if process_result_path.is_file() else None,
    )
