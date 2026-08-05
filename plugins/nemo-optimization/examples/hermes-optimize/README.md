# Hermes optimize examples

Fabric-backed numeric HPO demos for `nemo agents optimize`.

| File | Purpose |
|------|---------|
| `phishing.optimize.fabric-chatonly.yaml` | **Proven clean run** — chat-only Hermes, no MCP |
| `phishing.optimize.fabric-mcp.e2e.yaml` | Path-first MCP via platform `mcp_run_binding` (extended HPO) |
| `analyzer.inference-api.yaml` | Analyzer LLM settings for keys that work on inference-api |
| `package.yaml` / `agent.yaml` / `optimize.yaml` | Generic templates (`REPLACE_ME` models) |

Paired CLI and Python SDK recipes below. The same flows are also documented under
`docs/agents/optimization.mdx` (Optimize Agents) with CLI / Skill / SDK tabs.

## Prerequisites

From the `nemo-platform` repo root:

1. **Sync agents + Fabric-related workspace packages** (pulls `nemo-agents-plugin`,
   `nemo-optimization-plugin`, and locked Fabric adapters):

   ```bash
   uv sync --package nemo-agents-plugin
   ```

2. **`hermes-agent` harness (required for live Hermes runs)**  
   The workspace installs `nemo-fabric-adapters-hermes` **without** the `[harness]` extra
   (AIRCORE-952 / known pin conflicts: `hermes-agent` wants `requests==2.33.0` and
   historically `pillow==12.2.0`, which fight the lock). Until that is fixed upstream,
   install the harness into the project venv with:

   ```bash
   uv pip install --python .venv/bin/python "hermes-agent==0.18.2" --no-deps
   ```

   Confirm:

   ```bash
   .venv/bin/python -c "import hermes_cli; print('ok')"
   ```

3. **Fabric Hermes MCP (FABRIC-167)** — Hermes 0.18+ needs `discover_mcp_tools()` after
   the adapter writes `config.yaml`, and capability planning must preserve
   `mcp.servers.*.env`. Install a Fabric **0.2.0+** build that includes that fix, then
   always use `uv run --no-sync` so the lock does not downgrade Fabric to 0.1.0:

   ```bash
   # Build wheels in a NeMo-Fabric checkout (produces dist/*.whl):
   #   cd /path/to/NeMo-Fabric && just wheels
   export NEMO_FABRIC_DIST="${NEMO_FABRIC_DIST:-$HOME/work/NeMo-Fabric/dist}"

   uv pip install --python .venv/bin/python \
     --find-links "$NEMO_FABRIC_DIST" \
     --force-reinstall --no-deps \
     "nemo-fabric==0.2.0" \
     "nemo-fabric-adapters-hermes==0.2.0"
   ```

   Adjust the version pins to match the wheels in `$NEMO_FABRIC_DIST`
   (`ls "$NEMO_FABRIC_DIST"/nemo_fabric*.whl`).

4. `NVIDIA_API_KEY` in the environment. For `https://inference-api.nvidia.com/v1`,
   list models your key can call (`GET /v1/models`) and use the **full id**
   (often `nvidia/meta/...`, not bare `meta/...`). Prefer models that emit structured
   `tool_calls` (e.g. `nvidia/meta/llama-3.1-70b-instruct`). `gpt-oss-20b` on this
   endpoint often puts the call in reasoning text instead.

`--optimize-config` must be an **absolute** path. Dataset / `base_dir` paths in the
YAML are relative to the process CWD — run from the repo root.

## Clean chat-only run

### CLI

```bash
cd /path/to/nemo-platform

uv run --no-sync --package nemo-agents-plugin nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/phishing.optimize.fabric-chatonly.yaml" \
  --workspace default
```

### Python SDK

```python
import os
from pathlib import Path

from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler

WORKSPACE = "default"
repo = Path("/path/to/nemo-platform").resolve()
optimize_config = (
    repo / "plugins/nemo-optimization/examples/hermes-optimize/phishing.optimize.fabric-chatonly.yaml"
).resolve()

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=WORKSPACE,
)

result = NemoJobScheduler().run_local(
    OptimizeJob,
    {
        "optimize_config": str(optimize_config),
        "workspace": WORKSPACE,
    },
    workspace=WORKSPACE,
    sdk=client,
)
print(result)
```

Expected: Optuna study completes (`n_trials: 2`), `status: completed`.

## MCP: two author paths

### Static MCP (no hook)

Declare `mcp.servers` with `url`, `exposure`, and `env`. No `eval.run_hook`. Use this when
the MCP binary is fixed for every trial.

### Bound MCP (path-first, advanced)

For per-task private MCP bindings + audit (phishing-style), use the platform hook
`type: mcp_run_binding`. **Do not** pip-install the agent into the platform venv:

- `agent_src` — checkout `.../src` prepended for binding/handoff imports
- `executable` — MCP console from the **agent’s own** `.venv`
- `mcp.servers.<name>.env` — credentials for the MCP process
- `bindings[]` — lifecycle only (binding ref, executable, config_paths, optional handoff)

One-time agent checkout setup (separate venv):

```bash
export PHISHING_AGENT_ROOT="${PHISHING_AGENT_ROOT:-$HOME/work/email-phishing-analyzer-harnesses}"
cd "$PHISHING_AGENT_ROOT" && uv sync
export PHISHING_AGENT_SRC="$PHISHING_AGENT_ROOT/src"
export PHISHING_MCP_BIN="$PHISHING_AGENT_ROOT/.venv/bin/email-phishing-analyzer-mcp"
```

#### Bound MCP CLI

```bash
cd /path/to/nemo-platform

export PHISHING_AGENT_ROOT="${PHISHING_AGENT_ROOT:-$HOME/work/email-phishing-analyzer-harnesses}"
export PHISHING_AGENT_SRC="$PHISHING_AGENT_ROOT/src"
export PHISHING_MCP_BIN="$PHISHING_AGENT_ROOT/.venv/bin/email-phishing-analyzer-mcp"

test -d "$PHISHING_AGENT_SRC" || { echo "missing PHISHING_AGENT_SRC=$PHISHING_AGENT_SRC"; exit 1; }
test -x "$PHISHING_MCP_BIN" || { echo "missing PHISHING_MCP_BIN=$PHISHING_MCP_BIN (uv sync in agent checkout)"; exit 1; }

uv run --no-sync --package nemo-agents-plugin nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/phishing.optimize.fabric-mcp.e2e.yaml" \
  --workspace default
```

#### Bound MCP Python SDK

```python
import os
from pathlib import Path

from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler

WORKSPACE = "default"
repo = Path("/path/to/nemo-platform").resolve()
agent_root = Path(os.environ.get("PHISHING_AGENT_ROOT", Path.home() / "work/email-phishing-analyzer-harnesses"))
os.environ.setdefault("PHISHING_AGENT_SRC", str(agent_root / "src"))
os.environ.setdefault("PHISHING_MCP_BIN", str(agent_root / ".venv/bin/email-phishing-analyzer-mcp"))

optimize_config = (
    repo / "plugins/nemo-optimization/examples/hermes-optimize/phishing.optimize.fabric-mcp.e2e.yaml"
).resolve()

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=WORKSPACE,
)

result = NemoJobScheduler().run_local(
    OptimizeJob,
    {
        "optimize_config": str(optimize_config),
        "workspace": WORKSPACE,
    },
    workspace=WORKSPACE,
    sdk=client,
)
print(result)
```

Expected: Optuna study completes (`n_trials: 4`), `status: completed`, best score `1.0`.

`analyzer.inference-api.yaml` overrides the agent’s default `integrate.api.nvidia.com`
base URL (401s for many keys that work on inference-api).

## Notes

- Optional `--agent` must be a platform agent name (`hermes-optimize-chatonly` or
  `default/hermes-optimize-chatonly`). Endpoint / URI forms (`http://...`,
  `https://...`, `file://...`) are rejected; use an inline Fabric package in
  `--optimize-config` when you are not referencing a stored agent.
- `eval` / `optimizer` are platform overlays; they are stripped before `Fabric.run`.
- `capture_trajectory: false` in these packages avoids requiring the Relay gateway binary
  for a first smoke. Set `true` after `script/dev-install-fabric.sh` if you need ATIF.
- Local Hermes runtimes write under `./artifacts/` in this directory (safe to delete).
- Dataset emails for MCP should be single-line: the analyzer binding requires an exact
  match on the tool `text` argument, and models often collapse newlines.
- Judge / agent endpoints in these examples may use local or LAN HTTP (e.g. IGW on
  `10.0.0.51:8080`); that is expected for local platform runs.
