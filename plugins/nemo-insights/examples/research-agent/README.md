# research-agent

A minimal research agent built on the [NVIDIA NeMo Agent Toolkit (NAT)](https://github.com/NVIDIA/NeMo-Agent-Toolkit): a [Tavily](https://tavily.com/) search tool wired into a ReAct agent backed by an NVIDIA NIM-hosted LLM.

The workflow is declared in [`workflow.yml`](./workflow.yml); `main.py` is a thin wrapper that loads `.env` and invokes NAT's Python API.

## Setup

```bash
cp .env.example .env   # fill in NVIDIA_API_KEY and TAVILY_API_KEY
uv sync
```

## Run

Via the Python wrapper:

```bash
uv run main.py "What did NVIDIA announce at GTC 2026?"
```

Or directly via the NAT CLI (equivalent):

```bash
uv run nat run --config_file workflow.yml --input "What did NVIDIA announce at GTC 2026?"
```

## Customize

Edit `workflow.yml` to swap the model, change the search depth, or tweak the system prompt. To list every knob NAT exposes for a given component type:

```bash
uv run nat info components -t llm_provider -q nim
uv run nat info components -t function    -q tavily_internet_search
```

## Run on NeMo Platform

This example uses local paths to the monorepo's `nemo-platform`, `nemo-platform-plugin`, and `nemo-insights-plugin` packages. Run `uv sync` from this directory to create its standalone environment.

### Start services

From this directory:

```bash
set -a && source .env && set +a   # exposes NVIDIA_API_KEY / TAVILY_API_KEY
uv run nemo services run          # boots 18 services on :8080 — leave running
```

Confirm the plugin loaded: `nemo plugins list` should include `insights`, and the startup banner should list the `insights` service.

### Start ClickHouse (for the `intake` service)

The platform's `intake` service persists spans/traces in ClickHouse, and `nemo services run` does not bring it up. Without it, every `/apis/intake/v2/...` route returns `503 ClickHouse spans storage unavailable`, and the OTLP trace exporter in [`workflow.yml`](./workflow.yml) will fail to land traces.

The quickest fix is to run a single ClickHouse container on the default port (`8123`):

```bash
docker run -d --name nemo-clickhouse \
  -p 8123:8123 -p 9000:9000 \
  clickhouse/clickhouse-server:24.3
```

`intake` looks for ClickHouse at `http://localhost:8123` by default; override with `NMP_INTAKE_CLICKHOUSE_URL` if you're pointing at a remote instance. Verify with:

```bash
curl -s http://localhost:8123/ping                                           # -> Ok.
curl -s http://localhost:8080/apis/intake/v2/workspaces/default/traces       # -> 200 with JSON
```

Tear it down with `docker rm -f nemo-clickhouse` when you're done.

### Configure a provider

In a second shell, register the NVIDIA Build provider and pick a default model:

```bash
set -a && source .env && set +a
uv run nemo setup --auto
```

### Register the workflow as an agent

`workflow.yml` is a valid NAT config and is accepted by the platform as-is. The model name must be the platform-registered entity ID (lowercase, hyphenated) — list available IDs with `uv run nemo models list`.

```bash
uv run nemo agents create --name research-agent \
  --agent-config workflow.yml \
  --description "Tavily-powered research agent"
uv run nemo agents deploy --agent research-agent
```

`deploy` blocks until the container reaches `running` and prints the deployment endpoint.

### Chat with the deployed agent

```bash
uv run nemo agents invoke --agent research-agent \
  --input "What did NVIDIA announce at GTC 2026?"
```

The response is an OpenAI-style chat completion. Inference goes through the platform's gateway, and Tavily search is invoked from inside the agent container.

### Inspect and tear down

```bash
uv run nemo agents list
uv run nemo agents deployments list
uv run nemo agents logs --agent research-agent

echo y | uv run nemo agents undeploy --agent research-agent
echo y | uv run nemo agents delete   research-agent
```

### Gotchas

- **Model name format.** NAT YAML accepts the `meta/llama-3.3-70b-instruct` style for direct NIM calls, but when the agent runs under the platform, NIM calls are routed through the inference gateway, which validates names as lowercase letters/digits/hyphens (2–63 chars). Use the hyphenated entity ID from `nemo models list` (e.g. `meta-llama-3-3-70b-instruct`).
- **Undeploy / delete prompt.** No `--yes` flag on this build — pipe `echo y |` for non-interactive use.
- **Editing `workflow.yml`.** The platform stores the YAML at create time. After edits, `undeploy` + `delete` + `create` + `deploy` to pick them up.
