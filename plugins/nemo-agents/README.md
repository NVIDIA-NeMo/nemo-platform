# nemo-agents plugin

A NeMo Platform plugin that brings NVIDIA Agent Toolkit (NAT) agent workflows into
the platform as first-class managed resources.

Agents are NAT workflow YAML files. The plugin provides:

- **CRUD** — store and version agent configs in the platform entity store
- **Deployment** — start/stop `nat start fastapi` servers via an in-memory controller
- **Gateway** — reverse-proxy agent traffic through `/apis/agents/…/-/…`
- **CLI** — `nemo agents` subcommand for platform-managed workflows
- **Evaluation** — delegate to `nat eval` against live agent endpoints

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python ≥ 3.11 | |
| NVIDIA Agent Toolkit runtime | installed by this plugin as `nvidia-nat-core >= 1.5.0, < 2.0` and `nvidia-nat-langchain >= 1.5.0, < 2.0` |
| NVIDIA Agent Toolkit eval/optimizer | installed by this plugin as `nvidia-nat-eval >= 1.5.0, < 2.0` and `nvidia-nat-config-optimizer >= 1.5.0, < 2.0` |
| NVIDIA API key | set `NVIDIA_API_KEY` |

Install the plugin from the repo root, after `uv sync`. This also installs the
required NAT runtime, eval, and config optimizer subpackages; no separate
`nvidia-nat[most]` install is needed.

```bash
uv pip install -e plugins/nemo-agents/
```

Verify it loaded:

```bash
nemo --help   # should show "agents" under Plugins
nat --help    # should show run, eval, optimize, start, …
```

> **Working directory:** All example commands that reference `examples/` use
> paths relative to the plugin directory.  Run them from `plugins/nemo-agents/`:
>
> ```bash
> cd plugins/nemo-agents/
> ```

---

## ReAct agent demo — Wikipedia search + datetime tools

`examples/react-agent.yml` uses `meta/llama-3.1-70b-instruct` with:

- `wiki_search` — searches Wikipedia (no API key needed)
- `current_datetime` — returns current UTC time

When deployed via the platform, the Inference Gateway URL is injected
automatically into the agent config — you only need to:

1. Create an `nvidia-build` inference provider pointing at NVIDIA Build
2. Create the agent and deploy it
3. Invoke through the gateway

### Step 1 — Start the platform

Run this in a **dedicated terminal** — it stays in the foreground.  Use a
separate terminal for all subsequent steps.

```bash
nemo services run
```

### Step 2 — Create an inference provider

In a new terminal, export the base URL once so all subsequent `nemo` commands
pick it up automatically:

```bash
export NMP_BASE_URL=http://127.0.0.1:8080
cd plugins/nemo-agents/
```

In production the `system/nvidia-build` provider is created automatically by
the platform seed job. For local development, create it manually:

```bash
# Store the API key as a secret
nemo secrets create ngc-api-key \
    --data "$NVIDIA_API_KEY"

# Create the model provider
nemo inference providers create nvidia-build \
    --host-url https://integrate.api.nvidia.com \
    --api-key-secret-name ngc-api-key
```

Wait for the models controller to discover served models and register model
entities:

```bash
nemo wait inference provider nvidia-build
```

### Step 3 — Create and deploy the agent

```bash
# Register the agent config with the platform
nemo agents create \
    --name react-agent \
    --agent-config examples/react-agent/react-agent.yml

# Deploy it.  ``deploy`` waits for the spawned subprocess to reach a
# terminal state (``running`` or ``failed``) by default and exits 0 only
# when the agent is actually serving — so the exit code reflects the
# real outcome instead of just "the API call succeeded".
nemo agents deploy --agent react-agent
```

The deploy command prints a status line each time the deployment changes
state:

```
Waiting for deployment 'react-agent-e5e29e05' (timeout=300s)...
  [  0s] status: pending
  [  1s] status: starting
  [ 38s] status: running
Deployment 'react-agent-e5e29e05' is running at http://127.0.0.1:49152
```

If the subprocess dies during startup, the command exits 1 with the failure
reason from the deployment entity (e.g. ``Process exited with code 1``).
Use ``nemo agents logs --agent react-agent`` to inspect the subprocess log
afterwards (see [Inspecting agent logs](#inspecting-agent-logs)).

For scripted pipelines that prefer to poll separately, pass ``--no-wait``
to restore the legacy fire-and-forget behaviour:

```bash
nemo agents deploy --agent react-agent --no-wait
nemo agents deployments wait --agent react-agent
```

### Step 4 — Invoke through the gateway

```bash
nemo agents invoke \
    --agent react-agent \
    --input "Who invented the telephone? Also, what time is it right now?"
```

Expected response:
```json
{
  "choices": [{
    "message": {
      "content": "Alexander Graham Bell invented the telephone. The current time is 2026-03-23 23:17:08 +0000.",
      "role": "assistant"
    }
  }]
}
```

The gateway URL is:
```
http://127.0.0.1:8080/apis/agents/v2/workspaces/default/agents/react-agent/-/v1/chat/completions
```

You can call it directly with any OpenAI-compatible client using the same path.

The agent is still running — continue to the [Evaluation](#evaluation) section
below, or see [Cleanup](#cleanup-optional) to tear everything down.

---

## Evaluation

Evaluation delegates to `nat eval`, which sends dataset questions to the
agent's `/generate/full` endpoint and scores responses with a judge LLM.

The agent must be deployed and running (see Step 3 above) before evaluating.

```bash
nemo agents evaluate \
    --eval-config examples/test-eval.yml \
    --agent react-agent
```

The `--agent` flag resolves the running deployment endpoint automatically and
passes it to `nat eval --endpoint`.

Expected output:
```
=== EVALUATION SUMMARY ===
Workflow Status: COMPLETED (workflow_output.json)
Total Runtime: ~1.8s

Per evaluator results:
| Evaluator   |   Avg Score | Output File         |
|-------------|-------------|---------------------|
| runtime     |        ~0.9 | runtime_output.json |
```

A non-zero `Avg Score` and `Total Runtime` confirms requests reached the agent
successfully.  (The `avg_workflow_runtime` metric reports average seconds per
request, so the score varies with network latency.)

### LLM-judge evaluation (requires a judge LLM)

`examples/calculator-agent/calculator-eval.yml` uses `tunable_rag_evaluator`
with an LLM judge. The judge's `model_name` is `${NEMO_DEFAULT_MODEL}`, which
resolves to whichever model your platform context has set as the default
(see `nemo_platform.config.get_context().default_model`); `base_url` and
`api_key` are auto-injected by the platform to route through the Inference
Gateway. Set the env var, or edit `llms.judge_llm.model_name` to pin a
specific VirtualModel registered in your workspace, then run:

```bash
export NEMO_DEFAULT_MODEL=nvidia-nemotron-3-super-120b-a12b   # or any registered VirtualModel
nemo agents evaluate run \
    --eval-config plugins/nemo-agents/examples/calculator-agent/src/calculator_agent/calculator-eval.yml \
    --agent calculator-agent
```

The job pre-flights every LLM `model_name` against
`sdk.inference.virtual_models.retrieve` before invoking `nat eval`, so a
missing or mistyped model fails fast with a message naming the model and
suggesting recovery options instead of an opaque subprocess error.

---

## Inspecting agent logs

Each deployed agent runs as a local `nat start fastapi` subprocess.  Its
stdout and stderr are captured to a log file so you can debug failed
deployments or trace bad behaviour after the fact.

```bash
# Print the full log for the latest deployment of an agent
nemo agents logs --agent react-agent

# Or pass an explicit deployment name
nemo agents logs react-agent-e5e29e05

# Tail the last 100 lines (useful for noisy long-running agents)
nemo agents logs --agent react-agent --tail 100

# Stream new output as it is written (Ctrl-C to stop)
nemo agents logs --agent react-agent --follow

# Print only the absolute log file path — handy in scripts
nemo agents logs --agent react-agent --path
```

### Where logs live on disk

Logs and rendered NAT configs are stored under the standard NMP user-data
directory, alongside the platform's other persistent local state:

```
$NMP_DATA_DIR/agents/system/<deployment-name>.log
$NMP_DATA_DIR/agents/system/<deployment-name>.yaml
```

`$NMP_DATA_DIR` resolves (in order) to:

1. `$NMP_DATA_DIR` if explicitly set
2. `$XDG_DATA_HOME/nemo` if XDG is set
3. `~/.local/share/nemo` (the default)

So on a default macOS install, logs live at
`~/.local/share/nemo/agents/system/<name>.log`.  This location was
previously buried inside the plugin source tree (`<plugin>/.tmp/system/`)
with a randomised filename — the new layout is documented, predictable,
and survives `/tmp/` cleanup on reboot.  Filenames are deterministic
(`<deployment-name>.log`), so `nemo agents logs` resolves the path
without round-tripping through the API.

> Note: this layout assumes the agents service runs on the same host as
> the CLI invoker — true for the current in-memory runner backend.  Once
> a remote backend (Docker / Kubernetes) lands, log retrieval should move
> to a server-side endpoint that streams content over HTTP.

---

## Cleanup (optional)

To remove all resources created during the walkthrough:

```bash
# Remove the agent deployment and agent entity
nemo agents undeploy --agent react-agent
nemo agents delete react-agent

# Remove the inference provider and API key secret
nemo inference providers delete nvidia-build
nemo secrets delete ngc-api-key
```

The platform process itself can be stopped with `Ctrl-C` in its terminal.

---

## Agent config format

Agent configs are standard NAT workflow YAML files. The platform stores them
as `nat-workflow-v1` entities. All NAT component types are supported.

**ReAct agent with tools** (`examples/react-agent.yml`):

```yaml
functions:
  wiki:
    _type: wiki_search           # Wikipedia search, no API key
  clock:
    _type: current_datetime      # current UTC time

llms:
  llm:
    _type: openai
    api_key: not-used            # injected by platform at deploy time
    model_name: nvidia-nemotron-3-nano-30b-a3b  # IGW entity name
    temperature: 0.0

workflow:
  _type: react_agent
  tool_names: [wiki, clock]
  llm_name: llm
  parse_agent_response_max_retries: 3
```

### Model names

The `model_name` field must use the IGW entity name format (normalized hyphens):

| Provider format | IGW entity name |
|---|---|
| `nvidia/nemotron-3-nano-30b-a3b` | `nvidia-nemotron-3-nano-30b-a3b` |

The models controller auto-creates entity names by normalizing slashes and dots
to hyphens.

### base_url injection

When the controller deploys an agent, it calls `inject_gateway_url()` which
sets `base_url` via `setdefault` on each `openai`/`nim` LLM in the config.
**Do not set `base_url` in configs intended for platform deployment** — leave
it absent so the injected gateway URL takes effect.

The injected URL format:
```
{NMP_BASE_URL}/apis/inference-gateway/v2/workspaces/{workspace}/openai/-/v1
```

---

## Performance tips

### First-deploy cold start

The first `nemo agents deploy` after installing packages is noticeably slower
than subsequent deploys because Python compiles `.pyc` bytecache files on first
import. Pre-compiling NAT's dependencies eliminates this overhead:

```bash
python -m compileall -q $(python -c "import nat; print(nat.__path__[0])") 2>/dev/null
python -m compileall -q .venv/lib/ 2>/dev/null
```

This can cut 20--40 seconds off the first deploy.

---

## Notes and known limitations

- **`tool_calling_agent`** is broken with `langchain-openai==1.1.x` due to a
  missing `_DirectlyInjectedToolArg` import. Use `react_agent` instead.

- **`nat eval --endpoint` payload mismatch**: `nat eval` sends
  `{"input_message": query}` to `/generate/full`, but NAT's own
  `nat start fastapi` server expects `{"query": ...}` for `chat_completion`
  and similar workflow types.  This causes 422 errors on every request when
  `--endpoint` points at a locally-run agent server.  Evaluation via
  `--endpoint` is only reliable against a platform-deployed agent (where the
  gateway handles the translation).

- **IPv6 / localhost**: Start the platform with
  `NMP_BASE_URL=http://127.0.0.1:8080` to ensure agent subprocess processes
  can reach the platform. Python's `httpx` resolves bare `localhost` to IPv6
  `::1` on macOS, which does not match an IPv4-only listener.
