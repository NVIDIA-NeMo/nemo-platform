# NeMo Insights

Optional NeMo Platform plugin for analyzing agent telemetry and persisting actionable insights.

## Install from the monorepo

```bash
uv sync --group insights
```

The plugin is intentionally not part of `enabled-plugins`.

## CLI

From an agent directory, Insights discovers `optimizer.yaml` in the current
directory or its parents. Start by checking the profile and its environment,
then run analysis:

```bash
cd <agent-directory>
uv run nemo insights doctor
uv run nemo insights analyze
```

The profile contract consumed by Insights is deliberately small:

```yaml
agent: research-agent
agent_spec: AGENT-SPEC.md  # optional
workspace: default         # optional; defaults to "default"
```

Only `agent`, `agent_spec`, and `workspace` are consumed by Insights.
Unknown experiment-owned fields are ignored, while the reserved `profile_dir`
field is rejected. `agent` is required. Relative `agent_spec` paths are
resolved relative to the profile. When it is omitted, Insights looks for
`AGENT-SPEC.md`, then `README.md`, beside the profile.

An adjacent `.env` is loaded when a profile is found, without replacing
variables already set in the shell. For this shared profile workflow,
`NMP_BASE_URL` is the only base-URL environment variable. Resolution order is
explicit command-line flags, then profile values (for `agent`, `agent_spec`,
and `workspace`) or `NMP_BASE_URL` (for the base URL), then the built-in
defaults. `--base-url` takes precedence over `NMP_BASE_URL`.

With a discovered profile, analysis reads and writes the shared local output at
`.nemo-optimizer/insights.yaml` beside `optimizer.yaml`. Pass
`--insights-file-output` to use a different file explicitly.

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
