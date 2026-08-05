# Hermes optimize examples

Runnable demos for `nemo agents optimize` using the Hermes Fabric harness.

**Convention:** files named `optimize-*.yaml` are passed to `--optimize-config`.
Agent entity YAML lives under `agents/` and is passed to `--agent-config`.

| Example | What it does | `--optimize-config` | Other |
|---------|--------------|---------------------|-------|
| **Chat-only** | Tunes temperature on a short Q&A agent (no tools) | [`optimize-chatonly.yaml`](optimize-chatonly.yaml) | [`dataset-chatonly.json`](dataset-chatonly.json) |
| **Chat-only + `--agent`** | Same study; agent body from a platform entity | [`optimize-chatonly-via-agent.yaml`](optimize-chatonly-via-agent.yaml) | [`agents/chatonly/agent.yaml`](agents/chatonly/agent.yaml) |
| **MCP** | Tunes temperature / top_p on a phishing agent that calls an MCP analyzer | [`optimize-mcp.yaml`](optimize-mcp.yaml) | [`dataset-mcp.json`](dataset-mcp.json) |

Official docs: [Optimize Agents](../../../../docs/agents/optimization.mdx).

---

## One-time setup (platform)

Run all commands from the **`nemo-platform` repo root**.

### 1. Install the agents CLI

```bash
uv sync --package nemo-agents-plugin
source .venv/bin/activate
nemo --help   # should list `agents`
```

### 2. Install the Hermes harness

The lockfile cannot pull `hermes-agent` yet (dependency pin conflict). Install it
into the same venv:

```bash
uv pip install --python .venv/bin/python "hermes-agent==0.18.2" --no-deps
python -c "import hermes_cli; print('ok')"
```

### 3. API key

```bash
export NVIDIA_API_KEY=...   # required for inference-api.nvidia.com
```

The example YAMLs call `https://inference-api.nvidia.com/v1` with full model ids
such as `nvidia/meta/llama-3.1-70b-instruct`. Confirm your key can list those
models (`GET /v1/models`).

### Common run rules

- Pass an **absolute** path to `--optimize-config` (the snippets below use `$(pwd)/...`).
- Paths inside the YAML (`dataset`, `base_dir`) are relative to your **current
  working directory** — stay at the repo root.
- Local Hermes output lands in `./artifacts/` under this folder (safe to delete).
- Point Fabric at the platform venv so Hermes adapters resolve:

  ```bash
  export ADAPTER_PYTHON="$(pwd)/.venv/bin/python"
  ```

  Without this, Fabric may pick a system Python and fail with
  `No module named 'nemo_fabric_adapters'`.

### Platform URL

```bash
export NMP_BASE_URL="${NMP_BASE_URL:-http://localhost:8080}"
# Optional alias used by some CLI paths:
export NEMO_BASE_URL="${NEMO_BASE_URL:-$NMP_BASE_URL}"
```

---

## Example 1 — Chat-only

No MCP, no extra checkouts. Good first smoke for optimize.

```bash
cd /path/to/nemo-platform
source .venv/bin/activate   # if not already

nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/optimize-chatonly.yaml" \
  --workspace default
```

**Success:** job finishes with `status: completed` and `n_trials: 2`.

Python equivalent:

```python
import os
from pathlib import Path

from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler

WORKSPACE = "default"
repo = Path("/path/to/nemo-platform").resolve()
optimize_config = (
    repo / "plugins/nemo-optimization/examples/hermes-optimize/optimize-chatonly.yaml"
).resolve()

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=WORKSPACE,
)
print(
    NemoJobScheduler().run_local(
        OptimizeJob,
        {"optimize_config": str(optimize_config), "workspace": WORKSPACE},
        workspace=WORKSPACE,
        sdk=client,
    )
)
```

---

## Example 1b — Chat-only with `--agent`

Same smoke as Example 1, but the agent body is a **platform-managed** entity.
[`optimize-chatonly-via-agent.yaml`](optimize-chatonly-via-agent.yaml) is an
overlay (optimizer + eval only). Optimize resolves `--agent`, translates
`nemo-agents-spec-v1` → Fabric, and merges the overlay.

### 1. Register the agent (once)

Point `--agent-config` at the **slim**
[`agents/chatonly/agent.yaml`](agents/chatonly/agent.yaml) file — not the
parent `hermes-optimize/` directory (that tree includes `artifacts/` and will
fail the fileset size check).

```bash
cd /path/to/nemo-platform
source .venv/bin/activate
export NMP_BASE_URL="${NMP_BASE_URL:-http://localhost:8080}"
export ADAPTER_PYTHON="$(pwd)/.venv/bin/python"

# Optional: retarget models to your platform IGW before create, e.g.
#   model: <your-igw-model-id>
#   base_url: http://localhost:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1
#   api_key_env: NEMO_AGENTS_IGW_API_KEY
# (Replace host/model with your NMP_BASE_URL and IGW model id; values are
# stored as-is at create time — no ${...} expansion for this path.)
# Defaults in agent.yaml use inference-api (same as optimize-chatonly.yaml).

nemo agents create \
  --name hermes-optimize-chatonly \
  --agent-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/agents/chatonly/agent.yaml" \
  --workspace default
```

For a local IGW, also export a key env (any non-empty value is fine if the
gateway does not check it):

```bash
export NEMO_AGENTS_IGW_API_KEY="${NEMO_AGENTS_IGW_API_KEY:-not-used}"
```

### 2. Run optimize against the stored agent

```bash
nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/optimize-chatonly-via-agent.yaml" \
  --agent hermes-optimize-chatonly \
  --workspace default
```

**Success:** same as Example 1 (`status: completed`, `n_trials: 2`), with log
line `Resolved agent 'hermes-optimize-chatonly' to platform agent ...`.

To replace the stored config after editing `agent.yaml`:

```bash
nemo agents delete hermes-optimize-chatonly --workspace default
# then re-run create
```

---

## Example 2 — MCP (phishing analyzer)

Same optimize flow, but the agent calls an **MCP email-phishing analyzer** on
each dataset row. That analyzer lives in a **separate** repo with its own
virtualenv — do not `pip install` it into the platform `.venv`.

### Extra setup (once)

1. Clone and sync the agent checkout (adjust the path if yours differs):

   ```bash
   export PHISHING_AGENT_ROOT="${PHISHING_AGENT_ROOT:-$HOME/work/email-phishing-analyzer-harnesses}"
   cd "$PHISHING_AGENT_ROOT"
   uv sync
   ```

2. Point the platform job at that checkout’s source tree and MCP binary:

   ```bash
   export PHISHING_AGENT_SRC="$PHISHING_AGENT_ROOT/src"
   export PHISHING_MCP_BIN="$PHISHING_AGENT_ROOT/.venv/bin/email-phishing-analyzer-mcp"

   test -d "$PHISHING_AGENT_SRC"
   test -x "$PHISHING_MCP_BIN"
   ```

`optimize-mcp.yaml` reads those two variables. It also loads
[`analyzer-inference-api.yaml`](analyzer-inference-api.yaml) so the analyzer
uses inference-api (many keys 401 against `integrate.api.nvidia.com`).
The dataset is the agent’s full eval set (5 emails: 3 phishing, 2 benign).

### Run

```bash
cd /path/to/nemo-platform
source .venv/bin/activate

# Re-export if this is a new shell:
export PHISHING_AGENT_ROOT="${PHISHING_AGENT_ROOT:-$HOME/work/email-phishing-analyzer-harnesses}"
export PHISHING_AGENT_SRC="$PHISHING_AGENT_ROOT/src"
export PHISHING_MCP_BIN="$PHISHING_AGENT_ROOT/.venv/bin/email-phishing-analyzer-mcp"

nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/optimize-mcp.yaml" \
  --workspace default
```

**Success:** job finishes with `status: completed`, `n_trials: 4`, and a best
score near `1.0` when the model follows the “call the analyzer once” prompt.

Python equivalent:

```python
import os
from pathlib import Path

from nemo_optimization.jobs.optimize import OptimizeJob
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.scheduler import NemoJobScheduler

WORKSPACE = "default"
repo = Path("/path/to/nemo-platform").resolve()
agent_root = Path(
    os.environ.get("PHISHING_AGENT_ROOT", Path.home() / "work/email-phishing-analyzer-harnesses")
)
os.environ.setdefault("PHISHING_AGENT_SRC", str(agent_root / "src"))
os.environ.setdefault("PHISHING_MCP_BIN", str(agent_root / ".venv/bin/email-phishing-analyzer-mcp"))

optimize_config = (
    repo / "plugins/nemo-optimization/examples/hermes-optimize/optimize-mcp.yaml"
).resolve()

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace=WORKSPACE,
)
print(
    NemoJobScheduler().run_local(
        OptimizeJob,
        {"optimize_config": str(optimize_config), "workspace": WORKSPACE},
        workspace=WORKSPACE,
        sdk=client,
    )
)
```

---

## Troubleshooting

| Symptom | Likely fix |
|---------|------------|
| `nemo: command not found` | `source .venv/bin/activate` after `uv sync --package nemo-agents-plugin` |
| `No module named hermes_cli` | Re-run the `hermes-agent==0.18.2 --no-deps` install |
| `No module named 'nemo_fabric_adapters'` | `export ADAPTER_PYTHON="$(pwd)/.venv/bin/python"` |
| Missing `PHISHING_AGENT_SRC` / MCP binary | Sync the phishing agent checkout; export both env vars before `optimize run` |
| Analyzer / LLM 401 | Confirm `NVIDIA_API_KEY` works on inference-api; keep using `analyzer-inference-api.yaml` |
| Dataset / config file not found | Run from the `nemo-platform` repo root |
| Agent create fails on fileset size / too many files | Pass `--agent-config` to `agents/chatonly/agent.yaml` (slim dir), not the parent examples folder |
| Optional `--agent ...` rejected for `http://` / `file://` | Pass a workspace agent name (e.g. `hermes-optimize-chatonly`), or omit `--agent` and use `--optimize-config` only |

Trajectory capture (`capture_trajectory`) is off in these YAMLs so you do not
need the Relay gateway for a first smoke. Turn it on only if you need ATIF
traces.
