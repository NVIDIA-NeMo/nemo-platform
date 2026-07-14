# Intake Service

Intake is the telemetry ingestion and read API for NeMo Platform. It stores span
and trace data in ClickHouse, accepts OpenTelemetry traces, and supports
post-hoc annotations and evaluator result lookup.

## API Surface

Active v2 workspace endpoints:

- `GET /apis/intake/v2/workspaces/{workspace}/spans`
- `GET /apis/intake/v2/workspaces/{workspace}/spans/groups`
- `GET /apis/intake/v2/workspaces/{workspace}/spans/{span_id}`
- `GET /apis/intake/v2/workspaces/{workspace}/traces`
- `GET /apis/intake/v2/workspaces/{workspace}/traces/{id}`
- `GET /apis/intake/v2/workspaces/{workspace}/annotations`
- `POST /apis/intake/v2/workspaces/{workspace}/annotations`
- `DELETE /apis/intake/v2/workspaces/{workspace}/annotations/{annotation_id}`
- `GET /apis/intake/v2/workspaces/{workspace}/evaluator-results`
- `POST /apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces`
- `POST /apis/intake/v2/workspaces/{workspace}/ingest/chat-completions`
- `POST /apis/intake/v2/workspaces/{workspace}/ingest/atif`

## Local Development

Run these commands from the repository root unless a command says otherwise.
Intake tests rely on shared platform test helpers, so use the root `uv`
environment instead of package-scoped `uv run --package ...` commands.

Prerequisite: Docker must be installed and running locally.

Start a local ClickHouse container for span and trace storage:

```bash
services/intake/scripts/spans/run_clickhouse.sh
```

Start Intake with the platform runner:

```bash
uv run nemo services run \
  --services auth,entities,intake \
  --host 127.0.0.1 \
  --port 8000
```

In another terminal, start Studio from the `web/` workspace with the Intake
feature flag enabled:

```bash
VITEST=true VITE_FF_INTAKE_ENABLED=true VITE_PLATFORM_BASE_URL=http://localhost:8000 \
  pnpm --filter nemo-studio-ui start -- --host 127.0.0.1
```

The Studio dev server is available at
`http://127.0.0.1:5173/workspaces/default/intake/traces`.

Configure your local OTLP/HTTP trace exporter, NeMo relay, or collector to send
spans to Intake:

```bash
export OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:8000/apis/intake/v2/workspaces/default/ingest/otlp/v1/traces
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
```

Send a minimal OTLP trace after the service is running:

```bash
uv run services/intake/examples/send_otel_sample.py
```

Read it back:

```bash
curl -i "http://127.0.0.1:8000/apis/intake/v2/workspaces/default/spans?filter[session_id]=sample-session"
```

Seed an Experiment rollup and read it back:

```bash
uv run services/intake/scripts/spans/seed_experiment_rollup_data.py
curl -s "http://127.0.0.1:8000/apis/intake/v2/workspaces/default/experiments/rollup-smoke-exp" | jq

# Optional larger local workload.
uv run services/intake/scripts/spans/seed_experiment_rollup_data.py \
  --experiment experiment-name \
  --base-url http://127.0.0.1:8000 \
  --runs 10 \
  --cases-per-run 10
```

## Testing

Focused route-surface test:

```bash
uv run --frozen pytest services/intake/tests/integration/test_intake.py -q
```

Focused ingest/read tests:

```bash
uv run --frozen pytest \
  services/intake/tests/integration/spans/test_chat_completions_ingest.py \
  services/intake/tests/test_atif_v17.py \
  -q
```

Run the full Intake service test suite:

```bash
make test-service SERVICE=intake
```

## Generated API Artifacts

Run `make refresh-openapi` after Intake route or schema changes. The Stainless
resource config lives in `sdk/stainless.yaml`.
