# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Generic helpers for running agent-eval benchmark bundles."""

from __future__ import annotations

from pathlib import Path

from nemo_evaluator_sdk.agent_eval.benchmarks import (
    AgentEvalBenchmark,
    AgentEvalBenchmarkBundle,
    AgentEvalBenchmarkEvaluationKind,
    AgentEvalBenchmarkReports,
    AgentEvalBenchmarkReportWriter,
)
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.types import AgentEvalRunConfig, AgentEvalRunResult, AgentEvalTarget
from nemo_evaluator_sdk.values import RunConfigOnlineModel


async def run_benchmark_bundle(
    *,
    bundle: AgentEvalBenchmarkBundle,
    output_dir: Path,
    run_id: str,
    target: AgentEvalTarget | None = None,
    params: RunConfigOnlineModel | None = None,
    report_writer: AgentEvalBenchmarkReportWriter | None = None,
) -> tuple[AgentEvalRunResult, AgentEvalBenchmarkReports]:
    """Run a loaded benchmark bundle through :class:`AgentEvaluator`."""
    if bundle.evaluation_kind == AgentEvalBenchmarkEvaluationKind.STORED_ATTEMPTS:
        if target is not None:
            raise ValueError("stored_attempts benchmark bundles must not be run with a target")
        if bundle.attempts is None:
            raise ValueError("stored_attempts benchmark bundles require attempts")
        result = await AgentEvaluator().run(
            tasks=bundle.tasks,
            attempts=bundle.attempts,
            config=AgentEvalRunConfig(
                output_dir=output_dir,
                run_id=run_id,
                params=params,
                benchmark=bundle.metadata,
                write_dashboard=report_writer is None,
            ),
        )
    elif bundle.evaluation_kind == AgentEvalBenchmarkEvaluationKind.LIVE_TARGET:
        if target is None:
            raise ValueError("live_target benchmark bundles require a target")
        if bundle.attempts is not None:
            raise ValueError("live_target benchmark bundles must not include attempts")
        result = await AgentEvaluator().run(
            tasks=bundle.tasks,
            target=target,
            config=AgentEvalRunConfig(
                output_dir=output_dir,
                run_id=run_id,
                params=params,
                benchmark=bundle.metadata,
                write_dashboard=report_writer is None,
            ),
        )
    else:
        raise ValueError(f"unsupported benchmark evaluation kind {bundle.evaluation_kind!r}")

    if report_writer is not None:
        reports = report_writer.write_reports(result, output_dir)
    else:
        reports = AgentEvalBenchmarkReports(paths=[result.dashboard_path] if result.dashboard_path is not None else [])
    return result, reports


def benchmark_report_writer(benchmark: AgentEvalBenchmark) -> AgentEvalBenchmarkReportWriter | None:
    """Return a benchmark's optional report writer implementation."""
    if isinstance(benchmark, AgentEvalBenchmarkReportWriter):
        return benchmark
    return None


def benchmark_report_paths(reports: AgentEvalBenchmarkReports) -> tuple[Path | None, Path | None]:
    """Return the SDK report path and primary benchmark report path."""
    if not reports.paths:
        return None, None
    sdk_dashboard_path = reports.paths[0]
    dashboard_path = reports.paths[1] if len(reports.paths) > 1 else sdk_dashboard_path
    return sdk_dashboard_path, dashboard_path
