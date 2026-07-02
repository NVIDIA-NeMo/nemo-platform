---
name: nemo-intake
description: >
  Ingest and query agent telemetry with NeMo Intake. Send traces (OTLP,
  chat-completions, ATIF) into the platform, query spans and traces back,
  and attach annotations or look up evaluator results. Use when the user
  asks where their traces are, wants to see what their agent did, or wants
  to annotate a session.
triggers:
  - show my traces
  - where are my agent traces
  - query my spans
  - send traces to nemo
  - annotate this session
  - agent telemetry
  - intake
not-for:
  - nemo-status (use for overall platform health, not telemetry queries)
  - nemo-evaluator (use to run evaluations; intake only stores/reads their results)
  - nemo-try-agent (use to send a query to a deployed agent)
  - nemo-setup (use to install or start the platform)
compatibility: nemo-platform >= 0.1.0; requires the `intake` service running and a reachable ClickHouse (Docker for the local container); ingest and annotation commands change state — queries are read-only.
maturity: beta
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read]
---

# NeMo Intake — agent telemetry

Ingest agent traces into the platform and query them back. Intake stores spans, traces, annotations, and evaluator results in ClickHouse, workspace-scoped under `/apis/intake/v2/workspaces/{workspace}/`.

## Pre-flight

Run both probes before anything else. If either fails, stop and report which one.

```bash
# 1. Platform up and ready?
curl -sS --connect-timeout 2 --max-time 5 http://localhost:8080/health/ready | grep -q ready && echo "PLATFORM_UP" || echo "PLATFORM_DOWN"

# 2. Intake reachable and backed by ClickHouse?
HTTP=$(curl -sS --connect-timeout 2 --max-time 5 -o /dev/null -w "%{http_code}" "http://localhost:8080/apis/intake/v2/workspaces/default/spans")
case "$HTTP" in
  200) echo "INTAKE_OK" ;;
  503) echo "INTAKE_UP_CLICKHOUSE_DOWN" ;;
  404) echo "INTAKE_SERVICE_NOT_RUNNING" ;;
  *)   echo "INTAKE_UNEXPECTED ($HTTP)" ;;
esac
```

| Probe result | Action |
|---|---|
| `PLATFORM_DOWN` | Route to `nemo-setup` and stop |
| `INTAKE_SERVICE_NOT_RUNNING` | The running service set does not include `intake`. Tell the user to restart with intake included, e.g. `nemo services run --services auth,entities,intake` (or the full service group). Do not restart services without asking. |
| `INTAKE_UP_CLICKHOUSE_DOWN` | ClickHouse is not reachable. Offer to start the local container (below) — ask before running Docker. |
| `INTAKE_OK` | Proceed |

Local ClickHouse container (only with the user's go-ahead):

```bash
docker run -d --name nemo-intake-clickhouse -p 8123:8123 -p 9000:9000 clickhouse/clickhouse-server:26.3
curl -s http://localhost:8123/ping   # expect: Ok.
```

In a source checkout, prefer `services/intake/scripts/spans/run_clickhouse.sh` (persistent data dir). Connection overrides use `NMP_INTAKE_CLICKHOUSE_URL/USER/PASSWORD/DATABASE` env vars on the platform process; defaults match the container above. Re-run probe 2 after starting ClickHouse — the schema bootstraps lazily on the first request.

## Route by intent

| User wants | Do |
|---|---|
| Send telemetry in | **Ingest** |
| See traces / spans / what the agent did | **Query** |
| Attach feedback, labels, notes | **Annotate** |
| See evaluation scores on spans | **Evaluator results** |
| Browse visually | **Studio** |

All commands accept `--workspace`; omitted, they use the CLI context's workspace. Keep ingest and query in the same workspace.

## Ingest

Three formats. Pick by what the user has:

- **OTLP** (agent already emits OpenTelemetry/OpenInference traces) — configure their exporter, don't post by hand:

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://localhost:8080/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

- **Captured chat completion** (raw OpenAI-compatible request/response pair):

```bash
nemo intake ingest chat-completions create \
  --request '<request JSON>' \
  --response '<response JSON>' \
  --session-id <session>
```

When the user has no session ID, generate one with `uuidgen` and tell them what it is — do not invent memorable-looking strings that could collide.

- **ATIF trajectory** (from NeMo Agent Toolkit or an eval run): `nemo intake ingest atif create --input-file <file.json>`. Check `--help` for field-level flags; do not guess the schema.

**Verify every ingest** by reading it back before reporting success:

```bash
nemo intake spans list --filter.session-id <session>
```

## Query

```bash
nemo intake traces list                                  # recent traces (root-span summaries)
nemo intake traces get <trace-id>
nemo intake spans list --filter.session-id <session>     # spans, richly filterable
nemo intake spans get <span-id>                          # full span incl. input/output
nemo intake spans groups list                            # aggregations
```

Useful span filters: `--filter.kind` (llm, tool, agent, chain, retriever, …), `--filter.status`, `--filter.model`, `--filter.provider`, `--filter.tool-name`, `--filter.agent-name`, `--filter.project`, `--filter.trace-id`. Time ranges go through `--filter '{"started_at": {"gte": "...", "lte": "..."}}'`. Add `--output-format json` when you need to parse.

## Annotate

```bash
nemo intake annotations create <name> \
  --kind feedback \
  --session-id <session> \
  --text "<free text>"
```

`--kind` is one of `feedback`, `label`, `note`, `metadata`. Add `--span-id` to target one span instead of the whole session. Verify with `nemo intake annotations list --filter.session-id <session>`. Delete only when the user explicitly asks (`nemo intake annotations delete <annotation-id>`).

## Evaluator results

Read-only lookup of scores written by evaluation runs:

```bash
nemo intake evaluator-results list
nemo intake spans evaluator-results list <span-id>
```

To *produce* results, route to `nemo-evaluator` — do not hand-write evaluator results unless the user explicitly wants to inject one.

## Studio

The Intake UI (trace list, trace detail waterfall) is behind a preview flag. If the user wants the visual view, Studio must run with `VITE_FF_INTAKE_ENABLED=true`; pages live at `/workspaces/<workspace>/intake/traces`.

## Gotchas

- **503 means ClickHouse, not intake.** The service starts fine without ClickHouse and fails per-request. Fix the connection, don't restart the platform.
- **Workspace mismatch is the top "my traces are missing" cause.** The OTLP endpoint embeds the workspace in its path; queries must use the same one.
- **OTLP bodies are capped at 5 MiB** by default (`NMP_INTAKE_OTLP_MAX_BODY_BYTES`). A `413` means batch smaller exports or raise the limit.
- **Telemetry expires.** Span and trace tables have a 90-day TTL. Old traces disappearing is retention, not data loss.
- **Experiments have no CLI.** Experiment/experiment-group leaderboards are API/SDK-only (`client.experiments`, `client.experiment_groups`). Say so instead of inventing `nemo intake experiments ...`.
- **Never fabricate telemetry to make a query demo work.** If there is nothing to read back, say the store is empty and offer the ingest path.
