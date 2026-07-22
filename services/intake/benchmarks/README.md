# Intake Load-Test Specification

Status: Proposed

Implementation status: ingest, Evaluation corpus setup, and isolated read
layers are available via `make benchmark-intake`,
`make benchmark-intake-seed-evaluations`, and `make benchmark-intake-read`.
They cover valid OTLP payload generation, deterministic/resumable Evaluation
setup, fixed-concurrency ingest and reads, aligned local resource sampling,
structured samples and summaries, and public-API verification. All generated
platform data is fixed to the `load-testing` workspace. The mixed workload is
also available; the ClickHouse query-log collector and report generator remain
to be implemented.

Run the current ingest-only layer with its smoke defaults:

```bash
make benchmark-intake
make benchmark-intake BENCHMARK_ARGS="--duration-seconds 30 --concurrency 8 --spans-per-request 50"
```

There is intentionally no workspace argument. The runner creates or reuses
only `load-testing` and sends every ingest and verification request there.

For local bottleneck attribution, pass the platform process and ClickHouse
container. The measured phase then records API, load-generator, and ClickHouse
resource samples under `resources/usage.jsonl` and summarizes peaks in
`summary.json`:

```bash
make benchmark-intake BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --duration-seconds 30 --concurrency 8 --spans-per-request 50 \
  --platform-pid 12345 --clickhouse-container nmp-intake-clickhouse"
```

This document specifies the initial load test for the Intake service. The test is
intended to characterize capacity, latency, and failure behavior for the small
number of write and read paths that carry the most performance risk. It is not a
general API performance suite.

Run a trace browse or large-trace detail scenario against an existing corpus:

```bash
make benchmark-intake-read BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --scenario traces-preview --duration-seconds 30 --concurrency 1 \
  --platform-pid 12345 --clickhouse-container nmp-intake-clickhouse"

make benchmark-intake-read BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --scenario trace-detail-transaction --trace-id <trace-id> --session-id <session-id> \
  --duration-seconds 30 --concurrency 1 --platform-pid 12345 \
  --clickhouse-container nmp-intake-clickhouse"
```

`trace-detail-transaction` follows the current Studio implementation: detailed
trace rollups, the first 1,000 summary spans, and up to 1,000 annotations are
requested concurrently. The summary preserves both logical-operation latency
and each component's latency and response size.

Seed the nominal Evaluation corpus. Progress is checkpointed every 100 sessions
under `artifacts/evaluation-corpus/`, so the same command resumes after an
interruption:

```bash
make benchmark-intake-seed-evaluations BENCHMARK_ARGS="--base-url http://127.0.0.1:8000"
```

The seeder creates the 100-Evaluation wide group, the 10,000-session deep
Evaluation, 20 spans per session, and two numeric evaluator results per
session. It uses one ATIF request per session as setup traffic; ATIF throughput
is not a measured result. The final check reads the Evaluation rollups through
the public API.

Run the Evaluation scenarios using the group id from
`artifacts/evaluation-corpus/seed-summary.json`:

```bash
make benchmark-intake-read BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --scenario evaluation-overview --experiment-group-id <wide-group-id> \
  --duration-seconds 30 --concurrency 1 --platform-pid <pid> \
  --clickhouse-container nmp-intake-clickhouse"

make benchmark-intake-read BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --scenario evaluation-sessions-metric --evaluation-name load-test-deep-evaluation \
  --duration-seconds 30 --concurrency 1 --platform-pid <pid> \
  --clickhouse-container nmp-intake-clickhouse"
```

After the nominal R3 measurements, add the one extra deep session and run the
bounded correctness probe:

```bash
make benchmark-intake-seed-evaluations BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --add-limit-probe-session"

make benchmark-intake-read BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --scenario evaluation-metric-limit-probe --evaluation-name load-test-deep-evaluation \
  --warmup-seconds 0 --duration-seconds 1 --operations 1"
```

Run the mixed workload with five separate clients and connection pools. Its
default measured duration is five minutes; shorten it only for a local smoke or
initial interference check:

```bash
make benchmark-intake-mixed BENCHMARK_ARGS="--base-url http://127.0.0.1:8000 \
  --experiment-group-id <wide-group-id> --trace-id <large-trace-id> \
  --session-id <large-trace-session-id> --platform-pid <pid> \
  --clickhouse-container nmp-intake-clickhouse"
```

The clients run OTLP ingest at 10 spans/request and c10, Evaluation overview
at c2, normal Evaluation sessions at c2, trace preview at c2, and the Studio
trace-detail transaction at c1. Each path writes its own raw samples and
summary; only the ingest component samples shared API/ClickHouse resources to
avoid five concurrent `docker stats` collectors.

The first completed run establishes a baseline. It does not introduce CI
performance gates until the workload has been repeated enough to establish
normal run-to-run variance.

## Goals

- Measure OTLP ingest throughput and latency as request concurrency and batch
  size increase.
- Determine whether ingest performance changes as stored span volume grows.
- Measure the expensive Evaluation rollup and per-session query paths against
  representative wide and deep datasets.
- Measure the trace browse and trace detail paths used by Studio, including a
  trace with many child spans.
- Measure read latency while OTLP ingest and ClickHouse background work are
  active.
- Find the first observable saturation point, or state that saturation was not
  reached within the tested matrix.
- Produce a reproducible report that identifies whether the API process,
  ClickHouse, or the load generator was the bottleneck.

## Non-goals

The initial test will not load-test:

- Experiment Group or Evaluation create, update, delete, pin, or unpin.
- Annotation or evaluator-result CRUD as standalone workloads.
- ATIF or chat-completions ingest.
- Every filter, sort, response mode, or pagination combination.
- Span grouping or direct span/session lookup as standalone workloads.
- Authentication-provider capacity.
- Multi-replica scaling, autoscaling, or failover.
- Long-duration soak behavior beyond the mixed workload defined below.

Evaluator results are still part of the seeded corpus because Evaluation
rollups join them. Their CRUD endpoints are setup mechanisms, not measured
targets.

## Guiding decisions

1. Use a typed Python load generator built on `httpx.AsyncClient` and the OTLP
   protobuf classes already in the workspace. AIPerf is inference-specific and
   does not fit these endpoints.
2. Use fixed-concurrency, closed-loop workloads for the first characterization.
   This is suitable for finding saturation. Open-loop arrival-rate and burst
   tests can be added after a production traffic model exists.
3. Generate OTLP payloads before each measured interval. Payload construction
   time must not be included in request latency.
4. Use public Intake APIs for measured traffic. Dataset setup may use a separate
   optimized seeding path, but the report must identify how every table was
   populated.
5. Use project-local output under `services/intake/benchmarks/artifacts/`.
6. Treat an HTTP 200 response containing a non-empty `errors` array as a failed
   ingest request.
7. Use one API replica for the initial report. Multi-replica scaling is a
   separate follow-up.

## System under test

### Local smoke topology

Local runs validate the harness and payloads. They are not publishable capacity
numbers.

- ClickHouse started by `services/intake/scripts/spans/run_clickhouse.sh`.
- `auth,entities,intake` mounted in one platform API process on port 8080.
- The load generator running as a separate local process.

The existing `plugins/nemo-insights/testbed/eval/stack.py` is a useful reference
for bringing up this stack in CI.

### Characterization topology

Publishable runs use three separately observable components in the same cluster:

- One load-generator pod.
- One NeMo Platform API pod with one Uvicorn process and Intake enabled.
- One ClickHouse pod with dedicated storage.

Traffic must use cluster networking. Do not send measured traffic through
`kubectl port-forward`.

The run metadata must record:

- NeMo Platform git commit and image digest.
- ClickHouse image, version, and relevant server settings.
- Load-generator image digest.
- Node type and cluster name.
- CPU and memory requests and limits for all three components.
- API replica count and Uvicorn worker count.
- ClickHouse storage class and initial free space.
- Full workload configuration and random seed.

Resources should remain fixed across comparable runs. If the load generator
becomes CPU-, memory-, connection-, or network-bound, the result is invalid and
must be rerun with a larger load-generator allocation.

## Test corpus

### Data invariants

Every generated request must satisfy these rules:

- Trace IDs and span IDs are unique unless the scenario explicitly exercises
  re-ingestion.
- Timestamps are current and fall inside Intake's 90-day retention window.
- Each session has one root span and a deterministic set of child spans.
- Root spans in an Evaluation contain `nemo.experiment.id` and
  `nemo.test_case.id`.
- Spans include a representative mix of agent, LLM, tool, evaluator, and
  guardrail kinds.
- LLM spans include token, cost, model, provider, agent name, and agent version
  attributes so metric rollups do real work.
- Each Evaluation session has numeric evaluator results for at least two
  evaluator names.
- Input and output payload sizes are deterministic and recorded in the run
  configuration.
- The random seed is fixed and recorded.

### Corpus shapes

Total span count alone does not describe the expensive queries. The report
corpus must contain these shapes:

| Shape | Purpose | Nominal shape |
|---|---|---:|
| Wide group | Evaluation overview hydration across many Evaluations | 100 Evaluations × 100 sessions × 20 spans = 200,000 spans |
| Deep Evaluation | Per-session queries and all-session metric sorting | 1 Evaluation × 10,000 sessions × 20 spans = 200,000 spans |
| Large trace | Trace detail and child-span listing | 10 traces × 1,000 spans = 10,000 spans |
| Background | Overall same-workspace volume outside the focal groups | Enough sessions and spans to reach the configured volume checkpoint |

The defaults are starting values, not product limits. They must be configurable
without changing code.

### Volume checkpoints

The required checkpoints are:

- Empty database, after schema bootstrap and warmup.
- 100,000 current spans.
- 1,000,000 current spans.

If the 1-million-span run is clean and time permits, add a 10-million-span
checkpoint. The 10-million checkpoint is informative but not required for the
initial report.

Background rows must use the same workspace as the measured reads so primary-key
pruning does not make the volume test meaningless.

At the 1-million-span checkpoint, re-ingest 10% of the span identities once with
a later event timestamp. This leaves multiple physical versions for
`ReplacingMergeTree` and exercises the `FINAL` and `argMax` query paths under a
realistic exporter-retry shape. The report must record both current logical rows
and physical stored rows.

## Measured workloads

All standalone scenarios use a 10-second warmup followed by a 60-second measured
interval. Warmup requests are excluded from results. The runner must allow these
durations to be overridden for smoke runs.

### I1: OTLP ingest

Target:

```text
POST /apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces
Content-Type: application/x-protobuf
```

Matrix:

| Spans per request | Concurrency levels |
|---:|---|
| 1 | 1, 10, 50 |
| 10 | 1, 10, 50 |
| 100 | 1, 5, 10, 25 |

The generator must maintain at most the configured number of in-flight
requests. Its HTTP connection-pool limit must be at least the scenario
concurrency.

Run the `100 spans/request, concurrency 10` case at every volume checkpoint to
detect degradation as stored data grows.

### R1: Evaluation overview transaction

Model the Studio page load as two requests started concurrently:

```text
GET /apis/intake/v2/workspaces/{workspace}/evaluations
    ?filter[experiment_group_id]={group}
    &filter[is_pinned]=true
    &sort=-pinned_at
    &page=1
    &page_size=100

GET /apis/intake/v2/workspaces/{workspace}/evaluations
    ?filter[experiment_group_id]={group}
    &filter[is_pinned]=false
    &page=1
    &page_size=50
```

One logical operation succeeds only if both requests succeed. Record each
request latency and the overall transaction latency.

Run at logical concurrency 1 and 5 against the wide-group corpus.

### R2: Evaluation sessions, normal sort

Target the Studio request shape:

```text
GET /apis/intake/v2/workspaces/{workspace}/evaluations/{evaluation}/sessions
    ?mode=preview
    &page=1
    &page_size=50
```

Run at concurrency 1 and 5 against the deep Evaluation.

### R3: Evaluation sessions, metric sort

Target the expensive pre-pagination aggregation path:

```text
GET /apis/intake/v2/workspaces/{workspace}/evaluations/{evaluation}/sessions
    ?mode=preview
    &sort=-cost_total_usd
    &page=1
    &page_size=50
```

Run at concurrency 1 and 3 against the deep Evaluation. Do not duplicate this
scenario for `tokens`; both fields share the same all-session aggregation path.

The nominal deep corpus has exactly 10,000 sessions, matching the current
supported metric-sort cap. Add one correctness probe with 10,001 selected
sessions and verify that the API returns the documented 413 rather than running
an unbounded query. The 413 probe is not a throughput scenario.

### R4: Trace browse

Target the default Studio list shape:

```text
GET /apis/intake/v2/workspaces/{workspace}/traces
    ?mode=preview
    &sort=-started_at
    &page=1
    &page_size=50
```

Run at concurrency 1 and 10. This exercises trace-index counting plus page-scoped
span rollups.

### R5: Trace detail transaction

Model the Studio detail page as three requests started concurrently:

```text
GET /apis/intake/v2/workspaces/{workspace}/traces/{trace_id}?mode=detailed

GET /apis/intake/v2/workspaces/{workspace}/spans
    ?filter[trace_id]={trace_id}
    &mode=summary
    &sort=started_at
    &page=1
    &page_size=1000

GET /apis/intake/v2/workspaces/{workspace}/annotations
    ?filter[session_id]={session_id}
    &sort=-created_at
    &page=1
    &page_size=1000
```

Run at logical concurrency 1 and 5 against a 1,000-span trace. Record component
and transaction latency separately.

### M1: Mixed ingest and reads

Run for five measured minutes:

- Background OTLP ingest at 10 spans/request and concurrency 10.
- Foreground Evaluation overview transactions at logical concurrency 2.
- Foreground normal Evaluation-session requests at concurrency 2.
- Foreground trace-browse requests at concurrency 2.
- Foreground large-trace detail transactions at logical concurrency 1.

Each workload gets a separate client and connection pool. Report ingest and each
read path independently. Do not combine their samples into one latency
distribution.

## Execution order

The report profile follows this order:

1. Start from an empty, ephemeral ClickHouse database.
2. Wait for API and ClickHouse readiness.
3. Send one valid OTLP request and verify it through the read API. This also
   excludes schema-bootstrap latency from measured scenarios.
4. Run the empty-database I1 matrix.
5. Seed the 100,000-span checkpoint and verify logical counts.
6. Run the canonical I1 case and one concurrency-1 pass of R1 through R5.
7. Seed the nominal report corpus and background rows to 1,000,000 current spans.
8. Re-ingest 10% of span identities and verify logical and physical counts.
9. Run the complete R1 through R5 matrix.
10. Run the canonical I1 case at the 1-million-span checkpoint.
11. Run M1.
12. Allow active requests to drain, capture final ClickHouse state, and verify
    persisted counts.
13. Repeat the canonical scenarios three times on the same fixed corpus:
    canonical I1, R1 concurrency 1, R2 concurrency 1, R3 concurrency 1, R4
    concurrency 1, and R5 concurrency 1.
14. Produce the report and preserve artifacts.

Seed time is reported separately and excluded from measured workload duration.

## Metrics

### Client metrics

Capture per scenario:

- Attempted, successful, and failed logical operations.
- HTTP status counts.
- Intake responses with non-empty ingest `errors`.
- Connection, read, write, pool, and overall timeout counts.
- Requests per second.
- Spans and uncompressed payload bytes per second for ingest.
- Latency minimum, mean, p50, p90, p95, p99, and maximum.
- Actual achieved concurrency.
- Wall-clock duration.

Keep raw request samples as JSON Lines so summaries can be regenerated without
rerunning the load test.

### Service metrics

Sample at least every five seconds:

- API container CPU and memory.
- ClickHouse container CPU and memory.
- Load-generator container CPU and memory.
- Container restarts and Kubernetes readiness.
- ClickHouse active parts, physical rows, compressed bytes, and disk free space.
- Active and queued ClickHouse merges.

When available, collect ClickHouse query-log rows covering the run window,
including query duration, rows read, bytes read, rows written, and peak memory.
Profiling and flame graphs are follow-up diagnostics, not required artifacts for
every run.

### Correctness checks

At every volume checkpoint:

- Compare expected unique span identities with `spans FINAL` current rows.
- Compare expected root traces with `trace_index FINAL` current rows.
- Compare expected evaluator-result rows with current evaluator-result rows.
- Read at least one generated Evaluation, session, trace, and span through the
  public API and verify its identity and aggregate counts.
- Confirm there were no unreported load-generator exceptions.

Any mismatch invalidates the performance results for that checkpoint.

## Result artifacts

Each invocation writes only under:

```text
services/intake/benchmarks/artifacts/runs/<run-id>/
  config.json
  metadata.json
  seed-summary.json
  summary.json
  samples/
    <scenario>.jsonl
  resources/
    containers.csv
    clickhouse-before.json
    clickhouse-after.json
    query-log.jsonl
  logs/
    platform.log
    clickhouse.log
    loadgen.log
  report.md
```

The `artifacts/` directory must be gitignored. Credentials and authorization
headers must never be written to configuration, logs, or artifacts.

`summary.json` must include enough metadata to compare runs without reading the
raw samples. At minimum, each scenario record includes:

```json
{
  "scenario": "ingest-100-c10",
  "volume_checkpoint": 1000000,
  "duration_seconds": 60,
  "concurrency": 10,
  "operations": 0,
  "successes": 0,
  "failures": 0,
  "requests_per_second": 0.0,
  "spans_per_second": 0.0,
  "latency_ms": {
    "mean": 0.0,
    "p50": 0.0,
    "p90": 0.0,
    "p95": 0.0,
    "p99": 0.0,
    "max": 0.0
  }
}
```

## Harness interface

The implementation should expose one root Make target:

```bash
make benchmark-intake BENCHMARK_ARGS="--profile smoke"
make benchmark-intake BENCHMARK_ARGS="--profile report --base-url http://intake-api:8080"
```

Required profiles:

- `smoke`: small corpus, one request per read transaction, and a 10-second
  ingest run. Intended for local validation.
- `report`: the full execution order in this specification.

Required runner capabilities:

- Run against a stack started by the harness or an existing base URL.
- Select or skip seeding, workloads, and volume checkpoints.
- Override duration, concurrency, batch size, corpus dimensions, and random
  seed through a checked-in YAML configuration.
- Use a dedicated workspace and run ID.
- Resume query-only work against an already seeded corpus after verifying its
  seed manifest.
- Exit nonzero on harness errors, unexpected HTTP responses, correctness
  failures, or incomplete scenarios.
- Preserve partial results when a scenario fails.
- Handle SIGINT/SIGTERM by stopping new requests, draining in-flight requests,
  writing partial artifacts, and cleaning up only processes it started.

The harness must not automatically delete shared platform or ClickHouse data.
Characterization runs should use an ephemeral namespace and volume so cleanup is
scoped and recoverable.

## Analysis and reporting

The generated report must include:

1. Executive summary and tested commit.
2. Exact topology and resource limits.
3. Corpus sizes, shapes, payload sizes, and version amplification.
4. Ingest throughput and latency by batch size and concurrency.
5. Canonical ingest performance at each volume checkpoint.
6. Read-path latency and throughput by scenario.
7. Mixed-workload results compared with isolated results.
8. API, ClickHouse, and load-generator resource plots or tables.
9. Errors, timeouts, non-empty ingest error bodies, and correctness results.
10. Saturation point and evidence for the identified bottleneck.
11. Run-to-run variance for repeated canonical scenarios.
12. Limitations and recommended follow-ups.

Do not classify client errors as service errors without checking API and
ClickHouse logs. Do not report a clean run if persisted counts do not match the
seed manifest.

## Performance gates

The first report is characterization only. It establishes observed values rather
than asserting unreviewed product SLOs.

After at least three comparable characterization runs:

1. Select a small regression subset from the canonical scenarios.
2. Check in reviewed baseline values and tolerances.
3. Gate on relative regressions in p95/p99 latency and throughput, not on one
   machine's absolute values alone.
4. Keep the full report profile manually triggered or scheduled; do not run the
   full million-span corpus on every pull request.

## Implementation deliverables

- Typed OTLP payload and corpus generator.
- Async workload runner with bounded concurrency and explicit connection pools.
- Corpus seeder and seed manifest.
- Correctness verifier.
- Resource and ClickHouse-state collector.
- Summary/analyzer and Markdown report generator.
- Local smoke orchestration.
- Kubernetes manifests for an isolated API, ClickHouse, and load-generator
  topology.
- `make benchmark-intake` target.
- Gitignored artifact layout.
- A completed initial report from the report profile.

## Definition of done

The load test is complete when:

- The smoke profile passes from a clean local checkout.
- The report profile runs against the isolated Kubernetes topology without
  manual intervention after startup.
- All required volume checkpoints and workloads complete or have an explicitly
  documented saturation/failure result.
- Persisted logical counts match the seed manifest at every measured checkpoint.
- The load generator has demonstrated resource headroom during measured runs.
- Partial and final artifacts are sufficient to regenerate all reported
  statistics.
- Canonical scenarios have three comparable repetitions.
- The report identifies the tested clean-capacity range, saturation behavior,
  dominant bottleneck, and untested limitations.
- No performance baseline is promoted to a CI gate without review.
