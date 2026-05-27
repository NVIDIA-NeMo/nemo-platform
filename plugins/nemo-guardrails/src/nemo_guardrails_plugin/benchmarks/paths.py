# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Path resolution for the nemo-guardrails IGW benchmark harness."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    """Filesystem layout for a single benchmark invocation."""

    nmp_repo_root: Path
    ng_repo_root: Path
    benchmark_dir: Path
    run_dir: Path
    log_dir: Path
    generated_dir: Path
    aiperf_output_dir: Path
    pids_file: Path
    nmp_data_dir: Path
    config_template: Path
    runtime_config: Path
    junit_path: Path
    aiperf_venv_dir: Path

    @property
    def run_id(self) -> str:
        return self.run_dir.name

    def ensure_directories(self) -> None:
        for path in (
            self.log_dir,
            self.generated_dir,
            self.aiperf_output_dir,
            self.nmp_data_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


def _now_run_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def discover_nmp_repo_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` until a directory containing pyproject.toml + plugins/ is found."""
    candidate = (start or Path(__file__)).resolve()
    for parent in (candidate, *candidate.parents):
        if (parent / "pyproject.toml").is_file() and (parent / "plugins").is_dir():
            return parent
    raise RuntimeError(f"Could not locate NMP repo root from {start or Path(__file__)}")


def default_ng_repo_root(nmp_repo_root: Path) -> Path:
    return (nmp_repo_root.parent / "NeMo-Guardrails").resolve()


def build_run_paths(
    *,
    nmp_repo_root: Path,
    ng_repo_root: Path,
    junit_dir: Path | None = None,
    run_id: str | None = None,
) -> RunPaths:
    """Compose the standard benchmark filesystem layout under the plugin's artifacts dir.

    ``junit_dir`` controls where ``report.xml`` is written. CI passes the repo root so
    that the artifact upload step finds it at the expected location.
    """
    benchmark_dir = nmp_repo_root / "plugins" / "nemo-guardrails" / "benchmarks"
    artifacts_dir = benchmark_dir / "artifacts"
    run_dir = artifacts_dir / "runs" / (run_id or _now_run_id())
    junit_target = (junit_dir or nmp_repo_root) / "report.xml"

    return RunPaths(
        nmp_repo_root=nmp_repo_root,
        ng_repo_root=ng_repo_root,
        benchmark_dir=benchmark_dir,
        run_dir=run_dir,
        log_dir=run_dir / "logs",
        generated_dir=run_dir / "generated",
        aiperf_output_dir=run_dir / "aiperf_results",
        pids_file=run_dir / "pids.txt",
        nmp_data_dir=artifacts_dir / "nmp-data",
        config_template=benchmark_dir / "configs" / "nmp_igw_guardrails_sweep_concurrency.yaml",
        runtime_config=run_dir / "generated" / "nmp_igw_guardrails_sweep_concurrency.yaml",
        junit_path=junit_target,
        # Cached aiperf venv lives outside the per-run dir so it's reused
        # across local runs but lives under the gitignored artifacts dir.
        aiperf_venv_dir=artifacts_dir / "venvs" / "aiperf",
    )
