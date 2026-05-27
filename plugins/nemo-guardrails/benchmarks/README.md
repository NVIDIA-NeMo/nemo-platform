# NeMo Guardrails Plugin Benchmarks

Local harness for benchmarking the `nemo-guardrails` Inference Gateway
middleware against the upstream NeMo Guardrails benchmark suite (mock LLMs +
AIPerf sweep).

The implementation lives in `nemo_guardrails_plugin.benchmarks` (under
`plugins/nemo-guardrails/src/`). The harness does **not** copy benchmark code
from the NeMo Guardrails repository; it expects a local checkout and runs its
benchmark modules with `PYTHONPATH` pointed at that checkout.

## Layout

```text
plugins/nemo-guardrails/benchmarks/
  configs/
    nmp_igw_guardrails_sweep_concurrency.yaml   # AIPerf sweep template
  artifacts/                                    # per-run outputs (gitignored)
  generated/                                    # placeholder; per-run artifacts live under artifacts/runs/
plugins/nemo-guardrails/src/nemo_guardrails_plugin/benchmarks/
  run.py             # entry point: `python -m nemo_guardrails_plugin.benchmarks.run`
  paths.py           # filesystem layout
  constants.py       # workspace / VM / provider names
  processes.py       # subprocess supervision (process groups + ExitStack)
  seeding.py         # NMP SDK calls (workspace, providers, GuardrailConfig, VM)
  aiperf_runner.py   # rewrite AIPerf config + invoke upstream sweep + collect results
  bootstrap.py       # manage the isolated venv that hosts the `aiperf` CLI
  shim.py            # tiny HTTP shim that satisfies AIPerf's `/v1/models` pre-check
  report.py          # emit JUnit XML
```

## Prerequisites

- This repo bootstrapped via `make bootstrap-python` (the harness runs in
  `.venv` and imports the NMP SDK from the workspace).
- A local NeMo Guardrails checkout. By default the harness looks at
  `../NeMo-Guardrails` relative to the NMP repo root.
- `uv` available on `PATH`.
- Ports `8000`, `8001`, `8080`, and `8090` available — unless you opt into
  reusing an already-running local NMP via `--reuse-services`. Port `8090` is
  used by an internal shim that satisfies AIPerf's hard-coded `/v1/models`
  health probe.

The harness has its own `pyyaml` + `httpx` requirements that are declared as
the `bench` extra on `nemo-guardrails-plugin`. The `make benchmark-guardrails`
target installs them automatically via `uv run --extra bench`; they are not
part of the plugin's runtime install.

The upstream `aiperf` CLI itself pins `aiofiles<24.2`, which conflicts with
NMP's evaluator-service. To avoid downgrading the shared workspace venv, the
harness creates an isolated venv at
`plugins/nemo-guardrails/benchmarks/artifacts/venvs/aiperf/` on first run and
reuses it on subsequent runs. CI gets a fresh one each invocation; locally
this caches across runs for fast iteration.

## Run locally

From the NMP repo root:

```bash
make benchmark-guardrails
```

If your NeMo Guardrails checkout is somewhere else:

```bash
NEMO_GUARDRAILS_REPO_ROOT=/path/to/NeMo-Guardrails make benchmark-guardrails
```

To pass through arbitrary harness flags:

```bash
make benchmark-guardrails BENCHMARK_ARGS="--verbose --reuse-services"
```

The default sweep runs concurrency levels:

```text
1, 2, 4, 8, 16, 32, 64
```

With the default 60-second benchmark duration, expect ~10 minutes after
service bootstrap.

## What the harness starts

- The upstream benchmark **mock app LLM** on `http://localhost:8000`,
- The upstream benchmark **mock content-safety LLM** on `http://localhost:8001`,
- Local **NMP services** on `http://localhost:8080`, unless `--reuse-services`.

It then seeds NMP via the SDK with:

- workspace `benchmark`,
- app model provider `benchmark-app-llm`,
- content-safety model provider `benchmark-content-safety-llm`,
- guardrail config `content-safety-local`,
- VirtualModel `benchmark/guardrails-vm` with `nemo-guardrails` attached to
  both request and response middleware.

The benchmark target is:

```text
http://localhost:8080/apis/inference-gateway/v2/workspaces/benchmark/openai/-/v1/chat/completions
```

## Useful flags / environment

The harness accepts both CLI flags and environment variables:

| CLI flag                          | Environment variable             | Default                |
|-----------------------------------|----------------------------------|------------------------|
| `--nemo-guardrails-repo-root`     | `NEMO_GUARDRAILS_REPO_ROOT`      | `../NeMo-Guardrails`   |
| `--reuse-services`                | `NMP_BENCHMARK_REUSE_SERVICES=1` | start `nemo services run` |
| `--keep-running`                  | `NMP_BENCHMARK_KEEP_RUNNING=1`   | tear down on exit      |
| `--mock-workers`                  | `NMP_BENCHMARK_MOCK_WORKERS`     | `4`                    |
| `--junit-path`                    | _n/a_                            | `<repo-root>/report.xml` |
| `--run-id`                        | _n/a_                            | current timestamp      |

`--keep-running` leaves child processes alive for post-mortem inspection; the
list of PIDs is recorded in the per-run directory's `pids.txt`.

## Outputs

Each run writes artifacts under:

```text
plugins/nemo-guardrails/benchmarks/artifacts/runs/<timestamp>/
  logs/
    mock-app-llm.log
    mock-content-safety-llm.log
    nmp-services.log
    aiperf.log
  generated/
    app_provider.json
    content_safety_provider.json
    virtual_model.json
    content_safety_local_nmp_request.json
    nmp_igw_guardrails_sweep_concurrency.yaml   # runtime AIPerf config
  aiperf_results/<batch>/<timestamp>/<sweep-label>/
    run_metadata.json
    process_result.json
    profile_export*.json                         # written by aiperf
  pids.txt
```

`report.xml` is written to the repo root by default so CI's
`actions/upload-artifact` step picks it up at the same path as other test
suites. Override with `--junit-path`.

## CI

A `benchmark-guardrails` job in `.github/workflows/ci.yaml` checks out both
this repo and `NVIDIA/NeMo-Guardrails`, runs `make bootstrap-python` and
`make benchmark-guardrails`, and uploads the per-run artifacts directory plus
`report.xml` (so GitHub renders sweep pass/fail in the PR view).

Pass/fail is currently driven purely by `aiperf` exit code; no latency
thresholds are enforced.

## Cleanup

By default the harness only stops processes it started. It does not kill
unrelated processes on ports `8000`, `8001`, or `8080`.

Local NMP state is isolated by default under:

```text
plugins/nemo-guardrails/benchmarks/artifacts/nmp-data
```

Delete that directory for a completely fresh local benchmark state.
