# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run smoke-agent checks in parallel and maintain a live Markdown report.

Each pytest node runs in its own process and owns one ``--basetemp`` directory.
This keeps Harbor, Experimentalist, and pytest artifacts separate while allowing
the runner to report an individual result as soon as it completes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

Status = Literal["queued", "running", "passed", "skipped", "failed", "blocked", "interrupted"]

_REPO_ROOT = Path(__file__).resolve().parents[5]
_PLUGIN_ROOT = _REPO_ROOT / "plugins" / "nemo-experimentalist"
_PLUGIN = "nemo-experimentalist-plugin"
_TEST_FILES = (
    "plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_assets.py",
    "plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_mode_1_loop_e2e.py",
    "plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_mode_2_loop_e2e.py",
)
_E2E_MARKERS = ("test_insight_driven_loop_", "test_repair_groups_improve_validation", "test_g4_rejects")


@dataclass(frozen=True)
class Case:
    """One independently runnable pytest node."""

    nodeid: str
    mode: str
    group: str
    e2e: bool


@dataclass
class CaseResult:
    """The current result and artifacts for one pytest node."""

    case: Case
    status: Status = "queued"
    elapsed_seconds: float | None = None
    artifact_dir: Path | None = None
    log_path: Path | None = None
    winner: str | None = None
    objective_metrics: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    regression_metrics: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    reason: str | None = None


def classify_node(nodeid: str) -> Case:
    """Classify one collected smoke-agent pytest node."""
    group_match = re.search(r"\[([^\]]+)\]$", nodeid)
    group = group_match.group(1) if group_match else "g4-dispatch-order" if "test_g4_" in nodeid else "fixture"
    if "mode_1" in nodeid:
        return Case(nodeid=nodeid, mode="mode-1", group=group, e2e=any(marker in nodeid for marker in _E2E_MARKERS))
    if "mode_2" in nodeid:
        return Case(nodeid=nodeid, mode="mode-2", group=group, e2e=True)
    return Case(nodeid=nodeid, mode="structural", group=group, e2e=False)


def collect_cases() -> list[Case]:
    """Collect every smoke-agent node without running it."""
    test_files = [str((_REPO_ROOT / path).relative_to(_PLUGIN_ROOT)) for path in _TEST_FILES]
    command = ["uv", "run", "--frozen", "--package", _PLUGIN, "pytest", "--collect-only", "-q", *test_files]
    result = subprocess.run(command, cwd=_PLUGIN_ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"pytest collection failed:\n{result.stdout}{result.stderr}")
    return [classify_node(line) for line in result.stdout.splitlines() if line.startswith("tests/")]


def build_image() -> None:
    """Build the shared Harbor image before scheduling any E2E work."""
    command = ["uv", "run", "--no-project", "scripts/build_image.py"]
    result = subprocess.run(command, cwd=_REPO_ROOT / "plugins/nemo-experimentalist/examples/smoke-agent", check=False)
    if result.returncode:
        raise RuntimeError("smoke-agent Docker image build failed")


def e2e_preflight_failure() -> str | None:
    """Return the reason E2E work cannot start, or ``None`` when it can."""
    result = subprocess.run(
        ["curl", "-sf", "http://localhost:8080/health/ready"], text=True, capture_output=True, check=False
    )
    if result.returncode:
        return "the local NeMo Platform is not ready at http://localhost:8080/health/ready"
    return None


def _safe_name(case: Case) -> str:
    """Return a stable filesystem-safe name for one node."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{case.mode}-{case.group}-{case.nodeid.rsplit('::', maxsplit=1)[-1]}")


def _display_name(case: Case) -> str:
    """Return a readable unique name for one collected pytest node."""
    return f"{case.mode}/{case.group}/{case.nodeid.rsplit('::', maxsplit=1)[-1]}"


def _case_dir(run_root: Path, case: Case) -> Path:
    """Return the directory reserved for one pytest node's artifacts."""
    return run_root / "cases" / _safe_name(case)


def _metric_pairs(experiment: Path, winner: str, targets: object) -> dict[str, tuple[float | None, float | None]]:
    """Read selected and baseline validation values for configured metric targets."""

    def metrics(label: str) -> dict[str, float]:
        metadata = experiment / "eval-and-optimize" / "agents" / label / "metadata.json"
        payload = json.loads(metadata.read_text(encoding="utf-8"))
        values = (payload.get("rewards", {}).get("validation") or {}).get("metrics") or {}
        return {str(name): float(value) for name, value in values.items()}

    baseline = metrics("agent-0")
    selected = metrics(winner)
    names = [
        target.get("name") for target in targets if isinstance(target, dict) and isinstance(target.get("name"), str)
    ]
    return {name: (baseline.get(name), selected.get(name)) for name in names}


def enrich_from_experiment(result: CaseResult) -> None:
    """Populate winner and metric comparisons when the node created an experiment."""
    if result.artifact_dir is None:
        return
    runs = sorted(result.artifact_dir.rglob("experiment/eval-and-optimize/run.json"))
    if not runs:
        return
    run_path = runs[-1]
    payload = json.loads(run_path.read_text(encoding="utf-8"))
    winner = payload.get("winner_agent")
    if not isinstance(winner, str):
        return
    result.winner = winner
    snapshot = payload.get("config_snapshot") or {}
    experiment = run_path.parents[1]
    try:
        result.objective_metrics = _metric_pairs(experiment, winner, snapshot.get("objective_function") or [])
        result.regression_metrics = _metric_pairs(experiment, winner, snapshot.get("regression_metrics") or [])
    except (KeyError, OSError, TypeError, ValueError) as exc:
        result.reason = f"could not read winner metrics: {exc}"


def classify_failure(log_text: str) -> str:
    """Return a short, deterministic reason for one failed pytest node."""
    categories = (
        (
            "generated task verifier results dropped authored metric keys",
            "generated metrics were not written into final verifier rewards",
        ),
        ("authored metrics did not change", "the generated objective did not discriminate a repair"),
        ("did not improve objective", "the selected winner did not improve an objective metric"),
        ("regressed", "the selected winner worsened a regression guardrail"),
        ("produced no reward.json", "a Harbor task did not produce a score"),
        ("produced no trace", "a Harbor trial did not write the required trace"),
        ("Docker", "Docker or Harbor execution failed"),
        ("LLM API error", "the model endpoint rejected or failed the request"),
        ("platform unreachable", "the local NeMo Platform was unavailable"),
    )
    lowered = log_text.lower()
    for needle, reason in categories:
        if needle.lower() in lowered:
            return reason
    tail = [line for line in log_text.splitlines() if line.strip()][-12:]
    return "\n".join(tail) if tail else "pytest failed without output"


def _format_metrics(metrics: dict[str, tuple[float | None, float | None]]) -> str:
    """Render baseline-to-winner metric comparisons in one compact cell."""
    if not metrics:
        return "—"
    return "; ".join(f"{name}: {before} → {after}" for name, (before, after) in sorted(metrics.items()))


def render_report(results: list[CaseResult], started: datetime) -> str:
    """Render the current execution state as Markdown."""
    counts = {
        status: sum(item.status == status for item in results)
        for status in ("queued", "running", "passed", "skipped", "failed", "blocked", "interrupted")
    }
    lines = [
        "# Smoke-agent test run",
        "",
        f"Started: {started.isoformat()}",
        "",
        "| queued | running | passed | skipped | failed | blocked | interrupted |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        f"| {counts['queued']} | {counts['running']} | {counts['passed']} | {counts['skipped']} | {counts['failed']} | {counts['blocked']} | {counts['interrupted']} |",
        "",
        "| Case | Result | Time | Winner | Objectives | Regressions | Artifacts | Log |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in results:
        artifact = str(item.artifact_dir) if item.artifact_dir else "—"
        log = str(item.log_path) if item.log_path else "—"
        elapsed = f"{item.elapsed_seconds:.1f}s" if item.elapsed_seconds is not None else "—"
        lines.append(
            f"| `{_display_name(item.case)}` | {item.status} | {elapsed} | {item.winner or '—'} | "
            f"{_format_metrics(item.objective_metrics)} | {_format_metrics(item.regression_metrics)} | `{artifact}` | `{log}` |"
        )
    failures = [item for item in results if item.status == "failed" and item.reason]
    if failures:
        lines.extend(["", "## Failures", ""])
        for item in failures:
            lines.extend([f"### {item.case.mode}/{item.case.group}", "", item.reason, ""])
    return "\n".join(lines) + "\n"


def write_report(path: Path, results: list[CaseResult], started: datetime) -> None:
    """Atomically refresh the live Markdown report."""
    temporary = path.with_suffix(".tmp")
    temporary.write_text(render_report(results, started), encoding="utf-8")
    temporary.replace(path)


def run_case(case: Case, run_root: Path) -> CaseResult:
    """Run one pytest node once and retain all of its output."""
    case_dir = _case_dir(run_root, case)
    case_dir.mkdir(parents=True, exist_ok=True)
    log = case_dir / "pytest.log"
    environment = os.environ.copy()
    if case.e2e:
        environment |= {"SMOKE_AGENT_IMAGE_BUILT": "1"}
    command = [
        "uv",
        "run",
        "--frozen",
        "--package",
        _PLUGIN,
        "pytest",
        case.nodeid,
        "-v",
        "--basetemp",
        str(case_dir / "pytest"),
    ]
    started = datetime.now(UTC)
    completed = subprocess.run(
        command,
        cwd=_PLUGIN_ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log.write_text(completed.stdout or "", encoding="utf-8")
    skipped = completed.returncode == 0 and re.search(r"\b\d+ skipped\b", completed.stdout or "") is not None
    result = CaseResult(
        case=case,
        status="skipped" if skipped else "passed" if completed.returncode == 0 else "failed",
        elapsed_seconds=(datetime.now(UTC) - started).total_seconds(),
        artifact_dir=case_dir,
        log_path=log,
    )
    enrich_from_experiment(result)
    if result.status == "failed":
        result.reason = result.reason or classify_failure(completed.stdout or "")
    if result.status == "skipped":
        result.reason = "pytest skipped this case; its E2E assertions did not run"
    return result


def run_stage(
    cases: list[Case], *, workers: int, run_root: Path, results: list[CaseResult], started: datetime, report: Path
) -> None:
    """Run one structural or E2E stage with bounded parallelism."""
    by_node = {item.case.nodeid: item for item in results}
    scheduled = iter(cases)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        pending: dict[concurrent.futures.Future[CaseResult], Case] = {}

        def schedule_next() -> bool:
            try:
                case = next(scheduled)
            except StopIteration:
                return False
            item = by_node[case.nodeid]
            item.status = "running"
            item.artifact_dir = _case_dir(run_root, case)
            item.log_path = item.artifact_dir / "pytest.log"
            pending[executor.submit(run_case, case, run_root)] = case
            write_report(report, results, started)
            return True

        for _ in range(min(workers, len(cases))):
            schedule_next()
        while pending:
            completed_futures, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed_futures:
                case = pending.pop(future)
                try:
                    completed = future.result()
                except BaseException as exc:
                    completed = CaseResult(case=case, status="interrupted", reason=str(exc))
                by_node[case.nodeid] = completed
                results[:] = [by_node[item.case.nodeid] for item in results]
                write_report(report, results, started)
                schedule_next()


def main() -> int:
    """Run the complete structural and E2E smoke-agent matrix once."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--mode", choices=("all", "mode-1", "mode-2"), default="all")
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("--workers must be positive")

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_root = (args.output_dir or Path("/tmp/nemo-experimentalist-smoke-e2e") / timestamp).resolve()
    run_root.mkdir(parents=True, exist_ok=False)
    report = run_root / "report.md"
    started = datetime.now(UTC)
    cases = collect_cases()
    if args.mode != "all":
        cases = [case for case in cases if case.mode == "structural" or case.mode == args.mode]
    results = [CaseResult(case=case) for case in cases]
    write_report(report, results, started)
    print(f"Live report: {report}", flush=True)

    structural = [case for case in cases if not case.e2e]
    e2e = [case for case in cases if case.e2e]
    run_stage(structural, workers=args.workers, run_root=run_root, results=results, started=started, report=report)
    if any(item.status != "passed" for item in results if not item.case.e2e):
        print(f"Structural checks failed; E2E stage not started. Report: {report}", file=sys.stderr)
        return 1
    if failure := e2e_preflight_failure():
        for case in e2e:
            item = next(item for item in results if item.case == case)
            item.status = "blocked"
            item.reason = failure
        write_report(report, results, started)
        print(f"E2E stage not started: {failure}. Report: {report}", file=sys.stderr)
        return 1
    if not args.skip_build:
        build_image()
    run_stage(e2e, workers=args.workers, run_root=run_root, results=results, started=started, report=report)
    unsuccessful = [item for item in results if item.status != "passed"]
    print(f"Complete: {len(results) - len(unsuccessful)} passed, {len(unsuccessful)} unsuccessful. Report: {report}")
    return 1 if unsuccessful else 0


if __name__ == "__main__":
    raise SystemExit(main())
