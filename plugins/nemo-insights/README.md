# NeMo Insights

Optional NeMo Platform plugin for analyzing agent telemetry and persisting actionable insights.

## Install from the monorepo

```bash
uv sync --group insights
```

The plugin is intentionally not part of `enabled-plugins`.

## CLI

```bash
uv run nemo insights analyze \
  --agent research-agent \
  --workspace default \
  --base-url http://localhost:8080

uv run nemo insights analysis enable --agent research-agent
uv run nemo insights analysis status
uv run nemo insights analysis disable --agent research-agent
```

`--base-url` defaults to `NMP_BASE_URL`, then `http://localhost:8080`.

## API and SDK

The service is mounted under:

```text
/apis/insights/v2/workspaces/{workspace}
```

The plugin SDK is available as `client.insights`, including:

- `client.insights.insights`
- `client.insights.analysis_configs`
- `client.insights.analysis_run_statuses`

## Configuration

Periodic analysis settings use the `NEMO_INSIGHTS_` environment prefix. For example:

```bash
export NEMO_INSIGHTS_ANALYST_FREQUENCY=daily
export NEMO_INSIGHTS_ANALYST_TIMEZONE=America/Denver
```

## Development

```bash
uv run --group insights pytest plugins/nemo-insights/tests
uv run ruff check plugins/nemo-insights
```

## Testbed

The analyst-only testbed is in [`testbed/`](testbed/). It can replay pinned
Intake traces or run Tau2 benchmarks before invoking `nemo insights analyze`.
