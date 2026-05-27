# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Top-level entry point for the nemo-guardrails IGW benchmark harness.

Replaces the previous ``run_igw_guardrails_benchmark.sh`` shell flow with a
single Python orchestrator. Phases:

1. Resolve paths and validate the upstream NeMo Guardrails checkout.
2. Write a per-run AIPerf config under ``runs/<id>/generated/``.
3. Start the two mock LLM servers from ``${NEMO_GUARDRAILS_REPO_ROOT}/benchmark``.
4. Start (or reuse) ``nemo services run``.
5. Wait for health, seed NMP resources via the SDK, smoke-test the VirtualModel.
6. Invoke ``python -m benchmark.aiperf run --config-file ...`` for the sweep.
7. Collect per-sweep results, emit ``report.xml``, exit non-zero on any failure.

Process supervision uses session-scoped subprocesses and an ``ExitStack`` so a
``SIGTERM`` from CI cleans up forked workers (e.g. ``uvicorn --workers 4``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
import yaml
from nemo_guardrails_plugin.benchmarks.aiperf_runner import (
    collect_sweep_results,
    rewrite_aiperf_config,
    run_aiperf_sweep,
)
from nemo_guardrails_plugin.benchmarks.bootstrap import (
    ensure_aiperf_venv,
    env_with_venv_on_path,
)
from nemo_guardrails_plugin.benchmarks.constants import (
    AIPERF_SHIM_BASE_URL,
    IGW_CHAT_PATH,
    JUNIT_SUITE_NAME,
    NMP_BASE_URL,
    NMP_HEALTH_PATH,
)
from nemo_guardrails_plugin.benchmarks.paths import (
    RunPaths,
    build_run_paths,
    default_ng_repo_root,
    discover_nmp_repo_root,
)
from nemo_guardrails_plugin.benchmarks.processes import (
    SupervisedProcess,
    supervised_processes,
    wait_http,
    write_pids_file,
)
from nemo_guardrails_plugin.benchmarks.report import (
    cases_from_sweep_results,
    write_junit_report,
)
from nemo_guardrails_plugin.benchmarks.seeding import SeededResources, seed_benchmark
from nemo_platform import NeMoPlatform

log = logging.getLogger("nemo_guardrails_plugin.benchmarks")

_MOCK_START_TIMEOUT_SECONDS = 60
_NMP_START_TIMEOUT_SECONDS = 180


_REQUIRED_NG_FILES = (
    Path("benchmark/aiperf/__main__.py"),
    Path("benchmark/aiperf/run_aiperf.py"),
    Path("benchmark/mock_llm_server/run_server.py"),
    Path("benchmark/mock_llm_server/configs/meta-llama-3.3-70b-instruct.env"),
    Path("benchmark/mock_llm_server/configs/nvidia-llama-3.1-nemoguard-8b-content-safety.env"),
    Path("examples/configs/content_safety_local/config.yml"),
    Path("examples/configs/content_safety_local/prompts.yml"),
)


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def _validate_ng_repo(ng_repo_root: Path) -> None:
    missing = [p for p in _REQUIRED_NG_FILES if not (ng_repo_root / p).is_file()]
    if missing:
        bullet = "\n  - ".join(str(ng_repo_root / p) for p in missing)
        raise FileNotFoundError(f"NeMo Guardrails checkout at {ng_repo_root} is missing required files:\n  - {bullet}")


def _build_mock_processes(paths: RunPaths, workers: int) -> list[SupervisedProcess]:
    """Spawn ``python -m benchmark.mock_llm_server.run_server`` for both mocks.

    Each child is given its own log file and a ``PYTHONPATH`` pointing at the
    upstream checkout so its imports resolve.
    """
    env = {"PYTHONPATH": str(paths.ng_repo_root)}
    workdir = paths.ng_repo_root / "benchmark"

    def spec(name: str, port: int, env_file: Path) -> SupervisedProcess:
        return SupervisedProcess(
            name=name,
            cmd=[
                sys.executable,
                "-m",
                "benchmark.mock_llm_server.run_server",
                "--workers",
                str(workers),
                "--port",
                str(port),
                "--config-file",
                str(env_file),
            ],
            log_path=paths.log_dir / f"{name}.log",
            cwd=workdir,
            env=env,
        )

    return [
        spec(
            "mock-app-llm",
            8000,
            paths.ng_repo_root / "benchmark/mock_llm_server/configs/meta-llama-3.3-70b-instruct.env",
        ),
        spec(
            "mock-content-safety-llm",
            8001,
            paths.ng_repo_root / "benchmark/mock_llm_server/configs/nvidia-llama-3.1-nemoguard-8b-content-safety.env",
        ),
    ]


def _build_nmp_process(paths: RunPaths) -> SupervisedProcess:
    return SupervisedProcess(
        name="nmp-services",
        cmd=["nemo", "services", "run"],
        log_path=paths.log_dir / "nmp-services.log",
        cwd=paths.nmp_repo_root,
        env={"NMP_BASE_URL": NMP_BASE_URL, "NMP_DATA_DIR": str(paths.nmp_data_dir)},
    )


def _build_aiperf_shim_process(paths: RunPaths) -> SupervisedProcess:
    """Run the shim that satisfies AIPerf's `/v1/models` pre-check.

    Without this, AIPerf's hard-coded `urljoin(base_url, "/v1/models")` probe
    would 404 against NMP and the sweep would never start. See
    `nemo_guardrails_plugin.benchmarks.shim` for details.
    """
    return SupervisedProcess(
        name="aiperf-shim",
        cmd=[sys.executable, "-m", "nemo_guardrails_plugin.benchmarks.shim"],
        log_path=paths.log_dir / "aiperf-shim.log",
        cwd=paths.nmp_repo_root,
    )


_SMOKE_TEST_TIMEOUT_SECONDS = 60
_SMOKE_TEST_POLL_INTERVAL_SECONDS = 1.0


def _smoke_test(seeded: SeededResources) -> None:
    """POST one chat-completion through the IGW VirtualModel before sweeping.

    Catches misconfigured guardrails / middleware wiring early so a sweep
    failure isn't ambiguous between "harness broken" and "benchmark regressed".
    We hit the IGW URL directly with ``httpx`` rather than going through the
    NMP SDK so the smoke test exercises the same path AIPerf will.

    IGW's VirtualModel cache refreshes asynchronously after creation, so the
    first few requests can 404 even though seeding succeeded. We retry on
    404/503 for up to ~60s before failing.
    """
    url = f"{NMP_BASE_URL}{IGW_CHAT_PATH}"
    payload = {
        "model": seeded.vm_ref,
        "messages": [{"role": "user", "content": "Hello, what can you do?"}],
        "max_tokens": 64,
        "stream": False,
    }

    deadline = time.monotonic() + _SMOKE_TEST_TIMEOUT_SECONDS
    last_response: httpx.Response | None = None
    while time.monotonic() < deadline:
        last_response = httpx.post(url, json=payload, timeout=60.0)
        if last_response.status_code < 400:
            body = last_response.json()
            if not body.get("choices"):
                raise RuntimeError(f"Smoke test response missing choices: {body}")
            return
        if last_response.status_code in (404, 503):
            log.info(
                "Smoke test got HTTP %d; waiting for IGW cache refresh",
                last_response.status_code,
            )
            time.sleep(_SMOKE_TEST_POLL_INTERVAL_SECONDS)
            continue
        break

    code = last_response.status_code if last_response is not None else "no response"
    text = last_response.text[:500] if last_response is not None else ""
    raise RuntimeError(f"Smoke test failed with HTTP {code}: {text}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="nemo-guardrails-benchmark",
        description="Run the nemo-guardrails IGW benchmark sweep.",
    )
    parser.add_argument(
        "--nemo-guardrails-repo-root",
        type=Path,
        default=Path(
            os.environ.get(
                "NEMO_GUARDRAILS_REPO_ROOT",
                str(default_ng_repo_root(discover_nmp_repo_root())),
            )
        ),
        help="Path to a local NeMo Guardrails checkout (default: $NEMO_GUARDRAILS_REPO_ROOT or ../NeMo-Guardrails).",
    )
    parser.add_argument(
        "--reuse-services",
        action="store_true",
        default=os.environ.get("NMP_BENCHMARK_REUSE_SERVICES", "0") == "1",
        help="Skip starting `nemo services run` and reuse an existing local NMP at :8080.",
    )
    parser.add_argument(
        "--keep-running",
        action="store_true",
        default=os.environ.get("NMP_BENCHMARK_KEEP_RUNNING", "0") == "1",
        help="Leave started processes alive after the sweep (debugging).",
    )
    parser.add_argument(
        "--mock-workers",
        type=int,
        default=int(os.environ.get("NMP_BENCHMARK_MOCK_WORKERS", "4")),
        help="uvicorn worker count for each mock LLM server.",
    )
    parser.add_argument(
        "--junit-path",
        type=Path,
        default=None,
        help="Path to write report.xml (default: <repo-root>/report.xml for CI compatibility).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override the per-run directory name (default: current timestamp).",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    _configure_logging(args.verbose)

    nmp_repo_root = discover_nmp_repo_root()
    ng_repo_root = args.nemo_guardrails_repo_root.resolve()
    _validate_ng_repo(ng_repo_root)

    paths = build_run_paths(
        nmp_repo_root=nmp_repo_root,
        ng_repo_root=ng_repo_root,
        junit_dir=args.junit_path.parent if args.junit_path else None,
        run_id=args.run_id,
    )
    if args.junit_path:
        paths = RunPaths(**{**paths.__dict__, "junit_path": args.junit_path.resolve()})
    paths.ensure_directories()

    log.info("Run directory: %s", paths.run_dir)
    log.info("NeMo Guardrails repo: %s", paths.ng_repo_root)

    rewrite_aiperf_config(
        template=paths.config_template,
        output=paths.runtime_config,
        output_base_dir=paths.aiperf_output_dir,
    )
    sweep_config = yaml.safe_load(paths.runtime_config.read_text(encoding="utf-8"))
    log.info(
        "AIPerf sweep: concurrency=%s, duration=%ss",
        sweep_config.get("sweeps", {}).get("concurrency"),
        sweep_config.get("base_config", {}).get("benchmark_duration"),
    )

    # Ensure the dedicated aiperf venv exists *before* we start any supervised
    # processes. A first-time install can take ~30s and we'd rather pay that
    # cost up front than during the NMP-services startup race.
    aiperf_python = ensure_aiperf_venv(paths.aiperf_venv_dir)
    log.info("Using aiperf python at %s", aiperf_python)

    processes_to_start: list[SupervisedProcess] = _build_mock_processes(paths, args.mock_workers)
    if not args.reuse_services:
        processes_to_start.append(_build_nmp_process(paths))
    # The AIPerf shim is harness-local; we always start it (it talks to NMP
    # over HTTP, so it doesn't care whether nemo services run is supervised
    # by us or already running externally).
    processes_to_start.append(_build_aiperf_shim_process(paths))

    with ExitStack() as stack:
        started = stack.enter_context(supervised_processes(processes_to_start))
        write_pids_file(paths.pids_file, started)
        if args.keep_running:
            # Pop the cleanup so processes outlive this script.
            stack.pop_all()

        wait_http(
            "http://localhost:8000/health",
            timeout_seconds=_MOCK_START_TIMEOUT_SECONDS,
            label="mock app LLM",
        )
        wait_http(
            "http://localhost:8001/health",
            timeout_seconds=_MOCK_START_TIMEOUT_SECONDS,
            label="mock content-safety LLM",
        )
        wait_http(
            f"{NMP_BASE_URL}{NMP_HEALTH_PATH}",
            timeout_seconds=_NMP_START_TIMEOUT_SECONDS,
            label="NMP services",
        )
        wait_http(
            f"{AIPERF_SHIM_BASE_URL}/__shim/health",
            timeout_seconds=_MOCK_START_TIMEOUT_SECONDS,
            label="AIPerf shim",
        )

        client = NeMoPlatform(base_url=NMP_BASE_URL)
        seeded = seed_benchmark(
            client,
            ng_repo_root=paths.ng_repo_root,
            generated_dir=paths.generated_dir,
        )

        log.info("Smoke testing %s", seeded.vm_ref)
        _smoke_test(seeded)

        log.info(
            "Starting AIPerf sweep against %s -> shim -> %s%s",
            AIPERF_SHIM_BASE_URL,
            NMP_BASE_URL,
            IGW_CHAT_PATH,
        )
        aiperf_exit = run_aiperf_sweep(
            ng_repo_root=paths.ng_repo_root,
            runtime_config=paths.runtime_config,
            log_path=paths.log_dir / "aiperf.log",
            python_executable=str(aiperf_python),
            extra_env=env_with_venv_on_path(paths.aiperf_venv_dir, {}),
        )

    sweep_results = collect_sweep_results(paths.aiperf_output_dir)
    cases = cases_from_sweep_results(sweep_results)
    if not cases:
        # AIPerf failed before producing per-sweep dirs; emit a synthetic failure
        # so CI surfaces something actionable instead of an empty report.
        from nemo_guardrails_plugin.benchmarks.report import JUnitCase

        cases = [
            JUnitCase(
                name="aiperf",
                classname=JUNIT_SUITE_NAME,
                time_seconds=0.0,
                passed=aiperf_exit == 0,
                failure_message=(f"aiperf exited with code {aiperf_exit} and produced no per-sweep results"),
                system_out=f"aiperf_output_dir={paths.aiperf_output_dir}",
            )
        ]
    write_junit_report(paths.junit_path, suite_name=JUNIT_SUITE_NAME, cases=cases)
    log.info("Wrote JUnit report to %s", paths.junit_path)

    failures = sum(1 for c in cases if not c.passed)
    log.info("Sweep summary: %d run(s), %d failure(s)", len(cases), failures)
    if failures or aiperf_exit != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
