# Intake load-test results

Date: 2026-07-22

Status: local characterization; not a production capacity guarantee

Benchmark branch: `intake-load-testing/brnewsom` at `90fcc0443b`

## Executive summary

The local Intake stack on ClickHouse `26.3.17.56` completed every measured
operation without an unexpected HTTP or ingest error. The corpus reached
3.8 million spans and included a 10,000-session Evaluation and a 2,000-span
trace.

Observed clean load points:

| Workload | Load | Throughput | p50 | Primary limit |
| --- | --- | ---: | ---: | --- |
| OTLP, 1 span/request | c50 | 53 spans/s | 895 ms | ClickHouse-client insert queue |
| OTLP, 50 spans/request | c4 | 867 spans/s | 266 ms | Per-request/batching overhead |
| OTLP, 2,000 spans/request | c8 | 28,415 spans/s | 543 ms | API CPU, 94% peak |
| Evaluation overview | c1 | 2.1 page loads/s | 461–464 ms | ClickHouse rollups |
| Evaluation sessions, normal sort | c1 | 10.7 requests/s | 91 ms | ClickHouse query work |
| Evaluation sessions, cost sort over 10,000 sessions | c1 | 4.0–4.5 requests/s | 217–249 ms | ClickHouse aggregation |
| Trace preview | c4 | 10.5 requests/s | 341 ms | ClickHouse rollups |
| Trace detail page | c4 | 17.7 page loads/s | 211 ms | API CPU/serialization |

The 10,001-session metric-sort guard returned HTTP 413 before aggregation. A
60-second mixed ingest/read run completed all 1,920 operations, but every path
lost 40–78% throughput versus its isolated baseline.

## Main concerns

1. Small OTLP batches are inefficient. One-span requests spend most of their
   time queued behind per-request ClickHouse inserts and asynchronous-insert
   waits; higher concurrency primarily increases latency.
2. Evaluation overview and trace preview compute broad rollups on read. These
   queries consume multiple ClickHouse CPUs and up to roughly 450 MiB per query.
3. Ingest and read workloads have weak isolation. Concurrent rollups increased
   ClickHouse query time by 1.6–3.5x in the mixed run.
4. Large trace responses move the bottleneck to the single API worker through
   response construction and JSON serialization.

The highest-value follow-up is reducing or isolating compute-on-read rollups,
then retesting the same mixed profile. Stored-volume scaling, exporter retry
versions, and production multi-replica topology remain unverified.

## Test environment

- MacBook Pro (`Mac17,2`), Apple M5, 10 cores, 24 GiB unified memory.
- API and load generator ran natively on macOS 26.5.2 using one Uvicorn worker.
- ClickHouse ran in Docker Desktop with 10 CPUs and 7.75 GiB shared VM memory.
- Other native processes and containers shared the machine.
- All generated platform data used workspace `load-testing`.

Workload definitions and reproduction commands are in [README.md](README.md).
Raw request and resource samples are kept locally under `artifacts/runs/` and
are intentionally ignored by Git.
