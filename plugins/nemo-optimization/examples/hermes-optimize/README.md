# Hermes optimize examples

Runnable demos for `nemo agents optimize` using the Hermes Fabric harness.

Pick one:

| Example | What it does | Config | Dataset |
|---------|--------------|--------|---------|
| **Chat-only** | Tunes temperature on a short Q&A agent (no tools) | [`chatonly.yaml`](chatonly.yaml) | [`dataset.chatonly.json`](dataset.chatonly.json) |
| **MCP** | Tunes temperature / top_p on a phishing agent that calls an MCP analyzer | [`mcp.yaml`](mcp.yaml) | [`dataset.mcp.json`](dataset.mcp.json) |

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

---

## Example 1 — Chat-only

No MCP, no extra checkouts. Good first smoke for optimize.

```bash
cd /path/to/nemo-platform
source .venv/bin/activate   # if not already

nemo agents optimize run \
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/chatonly.yaml" \
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
optimize_config = (repo / "plugins/nemo-optimization/examples/hermes-optimize/chatonly.yaml").resolve()

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

`mcp.yaml` reads those two variables. It also loads
[`analyzer.inference-api.yaml`](analyzer.inference-api.yaml) so the analyzer
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
  --optimize-config "$(pwd)/plugins/nemo-optimization/examples/hermes-optimize/mcp.yaml" \
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

optimize_config = (repo / "plugins/nemo-optimization/examples/hermes-optimize/mcp.yaml").resolve()

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
| Missing `PHISHING_AGENT_SRC` / MCP binary | Sync the phishing agent checkout; export both env vars before `optimize run` |
| Analyzer / LLM 401 | Confirm `NVIDIA_API_KEY` works on inference-api; keep using `analyzer.inference-api.yaml` |
| Dataset / config file not found | Run from the `nemo-platform` repo root |
| Optional `--agent ...` rejected for `http://` / `file://` | Pass a workspace agent name (e.g. `hermes-optimize-chatonly`), or omit `--agent` and use `--optimize-config` only |

Trajectory capture (`capture_trajectory`) is off in these YAMLs so you do not
need the Relay gateway for a first smoke. Turn it on only if you need ATIF
traces.
