# nemo-agents plugin

A NeMo Platform plugin that brings NVIDIA Agent Toolkit (NAT) agent workflows into
the platform as first-class managed resources.

Agents are NAT workflow YAML files. The plugin provides:

- **CRUD** — store and version agent configs in the platform entity store
- **Deployment** — start/stop `nat start fastapi` servers via an in-memory controller
- **Gateway** — reverse-proxy agent traffic through `/apis/agents/…/-/…`
- **CLI** — `nemo agents` subcommand for platform-managed workflows
- **Evaluation** — delegate to `nat eval` against live agent endpoints
- **Packaging** — containerize agents with a single `nemo agents package` command that progressively renders, builds, and publishes

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

## Packaging command — containerize agents as Docker images

The plugin ships a single `package` command that encapsulates the render →
validate → build → publish pipeline.  Flags control how far the pipeline
runs, so one command covers the entire inner-loop → outer-loop transition.
The command works locally — no running platform is required.

| Requirement | Notes |
|---|---|
| Docker | A running Docker daemon (Docker Desktop / Podman / etc.) |
| `jinja2` | `uv pip install 'nemo-agents-plugin[container]'` |
| `python-on-whales` | included in the `[container]` extra |

### Progressive pipeline

| Invocation | Stages run | Output |
|---|---|---|
| `package --no-build` | render | `Dockerfile` + `.dockerignore` |
| `package` *(default)* | render → validate → build | Local Docker image |
| `package --publish --registry <url>` | render → validate → build → publish | Local image + registry push |

Validation always runs before a build unless `--skip-validation` is passed.
`--no-build` skips the build (and therefore validation) and only emits files.

### `package` — render, build, and publish in one command

Render-only (inspect or edit the Dockerfile before building):

```bash
nemo agents package \
    --agent examples/react-agent.yml \
    --nat-version 1.5.0 \
    --no-build
```

Output:
```
Dockerfile written to examples/Dockerfile
.dockerignore written to examples/.dockerignore
```

Build (default — render + validate + build):

```bash
nemo agents package \
    --agent examples/react-agent.yml \
    --nat-version 1.5.0 \
    --tag my-agent:1.0
```

Output:
```
Building image 'my-agent:1.0' from context examples ...
Successfully built my-agent:1.0
Image ready: my-agent:1.0
```

Full pipeline — build and publish in one call:

```bash
nemo agents package \
    --agent examples/react-agent.yml \
    --nat-version 1.5.0 \
    --tag my-agent:1.0 \
    --publish --registry nvcr.io/my-org
```

Output:
```
Building image 'my-agent:1.0' from context examples ...
Successfully built my-agent:1.0
Image ready: my-agent:1.0
Tagging my-agent:1.0 -> nvcr.io/my-org/my-agent:1.0
Pushing nvcr.io/my-org/my-agent:1.0 ...
Successfully pushed nvcr.io/my-org/my-agent:1.0
Published: nvcr.io/my-org/my-agent:1.0
```

**With an existing Dockerfile** (skip the render stage entirely):

```bash
nemo agents package \
    --agent examples/react-agent.yml \
    --dockerfile examples/Dockerfile \
    --nat-version 1.5.0 \
    --tag my-agent:1.0
```

**Project mode** — if the agent ships inside a Python project, pass `--pyproject`:

```bash
nemo agents package \
    --agent configs/agent.yaml \
    --pyproject pyproject.toml \
    --nat-version 1.5.0
```

### Flag reference

**Pipeline control:**

| Flag | Default | Description |
|---|---|---|
| `--no-build` | `False` | Stop after render; emit Dockerfile + `.dockerignore` only |
| `--publish` | `False` | After building, tag and push to `--registry` |
| `--registry`, `-r` | *(none)* | Remote registry URL (required when `--publish` is set) |
| `--push-tag` | `<registry>/<tag>` | Override the fully-qualified remote tag |

**Source inputs:**

| Flag | Default | Description |
|---|---|---|
| `--agent`, `-c` | *(required)* | Path to the NAT workflow YAML |
| `--pyproject` | *(none)* | Path to `pyproject.toml` (enables project mode) |
| `--format` | `docker` | Packaging format. Only `docker` (Jinja2 Dockerfile) is implemented; `whl` is reserved for future wheel-based builds and is rejected at flag-validation time. |
| `--dockerfile` | *(render on-the-fly)* | Use an existing Dockerfile instead of rendering |
| `--template` | built-in | Path to an external Jinja2 Dockerfile template |

**Build options:**

| Flag | Default | Description |
|---|---|---|
| `--tag`, `-t` | `<agent-name>-<agent-id>:<agent-version>` | Image tag |
| `--platform` | local daemon's native platform | Target platform (e.g. `linux/amd64`). At most one value -- multi-arch builds via buildx are not yet implemented and are rejected at flag-validation time with an actionable message pointing at `docker buildx imagetools create`. |
| `--nat-version` | `$NAT_VERSION` env var, then a baked-in fallback (currently `1.7.0`) | NAT package version to install. Strongly recommended to pass explicitly so image tags, labels, and the `nvidia-nat[most]==<ver>` constraint are reproducible. When neither the flag nor the env var is set, the fallback is used and the CLI prints a warning. |
| `--output`, `-o` | `<config-dir>/Dockerfile` | Where to write Dockerfile (with `--no-build`) |
| `--skip-validation` | `False` | Bypass `validate_agent_config` before build |

**Hardening overrides:**

| Flag | Default | Description |
|---|---|---|
| `--allow-root` | `False` | Disable non-root `USER` hardening |
| `--no-ignore` | *(generates by default)* | Skip `.dockerignore` generation |

**OCI labels:**

| Flag | Default | Description |
|---|---|---|
| `--agent-version` | from pyproject or `YY.MM.DD` | Override agent version label |
| `--agent-author` | from `git config user.name` | Override agent author label |

### Full example — inspect, build, publish

```bash
# 1. Render the Dockerfile so you can review it
nemo agents package \
    --agent examples/react-agent.yml \
    --nat-version 1.5.0 \
    --agent-version 1.0.0 \
    --no-build

# 2. (Optional) Edit examples/Dockerfile, then build against the edited file
nemo agents package \
    --agent examples/react-agent.yml \
    --dockerfile examples/Dockerfile \
    --nat-version 1.5.0 \
    --tag my-react-agent:1.0.0

# 3. Build & publish in one step (when skipping the review step)
nemo agents package \
    --agent examples/react-agent.yml \
    --nat-version 1.5.0 \
    --tag my-react-agent:1.0.0 \
    --publish --registry nvcr.io/my-org
```

### Image tagging convention

When `--tag` is not provided, the image tag is computed automatically as:

```
<agent-name>-<agent-id>:<agent-version>
```

Each component is resolved through a fallback chain:

| Component | Resolution order |
|---|---|
| **agent-name** | `pyproject.toml` `[project].name` → config file stem (e.g. `react-agent` from `react-agent.yml`) |
| **agent-version** | `--agent-version` flag → `pyproject.toml` `[project].version` → today's date as `YY.MM.DD` |
| **agent-id** | Truncated (12-char) SHA-256 hash of the config YAML content (+ `pyproject.toml` content when present) |

Examples:

| Scenario | Tag |
|---|---|
| Standalone `react-agent.yml`, no flags | `react-agent-f7e8d9c0b1a2:26.04.10` |
| With pyproject (`name=calculator`, `version=2.3.0`) | `calculator-a1b2c3d4e5f6:2.3.0` |
| With `--agent-version 1.0.0` override | `react-agent-f7e8d9c0b1a2:1.0.0` |

The agent ID is **content-addressable** — identical config (and pyproject) content
always produces the same ID. Changing any line in either file produces a
different ID, giving every build a traceable fingerprint.

### OCI image labels

Generated Dockerfiles include image labels that follow the
[OCI Image Spec annotations](https://github.com/opencontainers/image-spec/blob/main/annotations.md).
Standard OCI keys are used where a mapping exists; agent-specific metadata uses
the `com.nemo.agent.*` namespace.

**Standard OCI labels:**

| Label | Value |
|---|---|
| `org.opencontainers.image.title` | Agent name (same as tag name component) |
| `org.opencontainers.image.version` | Agent version (same as tag version component) |
| `org.opencontainers.image.authors` | `--agent-author` → `git config user.name` → `"unknown"` |
| `org.opencontainers.image.created` | Build timestamp (ISO 8601 / RFC 3339) |
| `org.opencontainers.image.description` | `pyproject.toml` `[project].description` → `"{workflow._type} agent"` → `""` |
| `org.opencontainers.image.revision` | `git rev-parse HEAD` → `""` |
| `org.opencontainers.image.source` | `git remote get-url origin` → `""` |
| `org.opencontainers.image.licenses` | `pyproject.toml` `[project].license` (SPDX expression) — omitted when absent |

**Custom agent labels:**

| Label | Value |
|---|---|
| `com.nemo.agent.id` | Content-addressable SHA-256 hash (12 chars) |
| `com.nemo.agent.framework` | `"nemo_agent_toolkit"` when config has a `workflow` key, else `"unknown"` |
| `com.nemo.agent.nat-version` | NAT version used at build time |
| `com.nemo.agent.contract-version` | Packaging format version (`"1.0"`) |

### Agent config validation

The `package` command validates the agent config before building (skip with
`--skip-validation`). Validation checks:

- File is valid YAML that parses to a mapping (dict)
- Top-level `workflow` key exists and is a mapping
- `workflow._type` is present and non-empty (missing `_type` is an error; an
  unrecognized value — e.g. a workflow registered by a NAT plugin the
  validator does not know about — only emits a warning and the build
  proceeds). Built-in types: `react_agent`, `tool_calling_agent`,
  `reasoning_agent`, `rewoo_agent`
- Every name in `workflow.tool_names` is defined in `functions` or `function_groups`
- `workflow.llm_name` is defined in `llms`

Multiple errors are collected and reported together rather than failing on the first.

### Security defaults

Generated Dockerfiles apply several hardening measures by default:

| Default | Override |
|---|---|
| Non-root `USER agent` (uid 1000) | `--allow-root` |
| `apt-get --no-install-recommends` | *(none — always applied)* |
| `rm -rf /var/lib/apt/lists/*` after install | *(none — always applied)* |
| `.dockerignore` excludes `.env`, `.git/`, `*.pem`, `credentials.json`, `__pycache__/`, `.venv/`, `node_modules/` | `--no-ignore` |

### Rendering modes

The Dockerfile template has two modes, selected automatically:

| Mode | Trigger | Install strategy |
|---|---|---|
| **Config-only** | No `--pyproject` | `uv pip install "nvidia-nat[most]==${NAT_VERSION}"` |
| **Project** | `--pyproject` provided | `uv pip install .` (installs the project and its declared deps) |

In project mode the entire project directory is the build context and the config
path is resolved relative to the `pyproject.toml` parent directory.

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
