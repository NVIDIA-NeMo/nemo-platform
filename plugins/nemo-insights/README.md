# NeMo Insights

NeMo Platform plugin for analyzing agent telemetry and persisting actionable insights.

## Install from the monorepo

```bash
uv sync
```

The plugin is installed by default through the root workspace's `enabled-plugins` group.

## CLI

From an agent directory, Insights discovers `optimizer.yaml` in the current
directory or its parents. Start by checking the profile and its environment,
then run the analyst:

```bash
cd <agent-directory>
uv run nemo agents analyst doctor
uv run nemo agents analyst run
```

Run `nemo setup` first to select the default and fast Platform Model Entities.
The Analyst uses the default model for analysis and the fast model for context
summarization; an existing context without `fast_model` reuses `default_model`.
Provider credentials remain in Platform Secrets.

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

### Telemetry requirement

The analyst scopes Intake span queries to the configured `agent`. The normalized
`agent_name` on each span must therefore match `agent` in `optimizer.yaml` or
`--agent`. For OTLP, always set `gen_ai.agent.name` on every span; Intake also
normalizes `llm.agent.name` and `agent.name` from instrumentation that emits
those conventions. ATIF maps its required `agent.name` automatically.

### Where insights are written

Insights always go to the platform, through the Insights plugin API. There is no
mode that keeps them off it.

Pass `--insights-file-output <path>` to also keep a local copy: the platform is
written first and the file mirrors what it stored, platform ids included, so a
later run's updates land in both stores. Each run merges into the file rather
than overwriting it. Because the platform is the source of truth, a file that
cannot be written is reported as a warning on the run report instead of failing
the run.

```bash
uv run nemo agents analyst run                                  # platform only
uv run nemo agents analyst run --insights-file-output out.yaml  # platform + local mirror
```

```bash
uv run nemo agents analyst run \
  --agent research-agent \
  --workspace default \
  --base-url http://localhost:8080

uv run nemo insights analysis enable --agent research-agent
uv run nemo insights analysis status
uv run nemo insights analysis disable --agent research-agent
```

`analysis enable` stores the effective default/fast pair in the server-side
analysis config so scheduled jobs do not depend on the operator's local CLI
file. Re-run `enable` after changing the pair with `nemo setup`. Existing
enabled records created before model-pair persistence must also be re-enabled.

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
uv run pytest plugins/nemo-insights/tests
uv run ruff check plugins/nemo-insights
```

## Testbed

The analyst-only testbed is in [`testbed/`](testbed/). It can replay pinned
Intake traces or run Tau2 benchmarks before invoking `nemo agents analyst run`.
