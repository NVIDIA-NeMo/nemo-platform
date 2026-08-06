# Email Phishing Agent — Fabric example (`nemo-agents-spec-v1`)

A Platform-native port of the email-phishing analyzer, and a sibling to
[`../calculator-agent`](../calculator-agent). Unlike the NAT ReAct example
(`../../email-phishing-analyzer`), classification does **not** hide behind an
opaque MCP server. It runs as a Fabric **deepagents orchestrator** that
delegates the verdict to a phishing **subagent** and calls a deterministic
`extract_iocs` **tool** — so the prompt and model are tunable in config, and each
step (subagent task + tool call) emits a trace span.

## Shape

```
orchestrator (deepagents)  ── delegates ──▶  phishing-analyzer subagent
      │                                            │
      └──────────── calls ──────────────▶  extract_iocs (stdio MCP tool)
```

- **`agent.yaml`** — the `nemo-agents-spec-v1` config. Orchestrator triage prompt
  in `instructions.system`; the phishing subagent under
  `harnesses.deepagents.settings.deepagents.subagents`, with its own
  `system_prompt` and a loose YAML verdict (`is_likely_phishing`, `confidence`,
  `indicators`, `explanation`) the orchestrator parses; `extract_iocs` wired as a
  stdio MCP server.
- **`mcps/iocs.py`** — the `extract_iocs` tool: pure-regex URL/domain extraction
  (ported from the email-security-analyst example), served over stdio by the
  `email-phishing-iocs` console script.
- **`data/`** — `smaller_test.csv` plus `build_dataset.py`, which assembles a
  sender-inclusive `email` column (`From:`/`Subject:`/body). The sender is a top
  phishing tell and also feeds `extract_iocs`; the NAT eval dropped it by feeding
  `body` only.
- **`email-phishing-eval.yml`** — eval config; `question_key: email` (the
  assembled message, not bare `body`).

## Tune

- **Prompts:** edit `instructions.system.content` (orchestrator) or the subagent
  `system_prompt` in `agent.yaml`.
- **Hyperparameters:** `models.default.temperature` (and `settings`). Add a
  per-subagent `model: <provider>:<model>` to tune the analysis step
  independently of the orchestrator.

## Run

`extract_iocs` runs as a **stdio MCP server that Fabric launches as a parallel
child process** of the agent: the deepagents adapter expands and `shlex`-splits
the `url`, then spawns it, resolving the command on `PATH`. So the console
script must exist in the environment the agent actually runs in — which differs
by deployment mode. (deepagents adapter + `NVIDIA_API_KEY` required either way.)

### Local (`--mode subprocess`, the default)

This example is a uv workspace member, so `uv sync --all-packages` already
installed `email-phishing-iocs` into the repo `.venv`. The subprocess deployment
runs from that same venv (`sys.executable`) and inherits its `PATH`, so Fabric
can spawn the tool — no extra install and no image needed:

```bash
nemo agents create  --name email-phishing-agent \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/agent.yaml
nemo agents deploy  --agent email-phishing-agent --name email-phishing-agent-deployment --mode subprocess
nemo agents invoke  --agent-deployment email-phishing-agent-deployment \
  --input "From: it-support@paypa1-secure.example
Subject: Verify your account

Your account is locked. Confirm your password at http://paypa1-secure.example/login"
```

### Container (`--mode docker` / `k8s`)

A deployment container does **not** have this example installed, so a local
`uv pip install` cannot reach it. Bake the package into an image with
`nemo agents package` — project mode (`--pyproject`) runs `uv pip install .`,
which provides the `email-phishing-iocs` console script — then deploy that image:

```bash
nemo agents package \
  --agent plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/agent.yaml \
  --pyproject plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/pyproject.toml \
  --tag email-phishing-agent:local

nemo agents create  --name email-phishing-agent \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/agent.yaml
nemo agents deploy \
  --agent email-phishing-agent \
  --name email-phishing-agent-deployment \
  --mode docker \
  --image email-phishing-agent:local
```

For Kubernetes, publish the image
(`nemo agents package ... --publish --registry <registry>`) and pass the
published image to `nemo agents deploy --mode k8s --image <image>`.

Evaluate against the sender-inclusive dataset:

```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/email-phishing-eval.yml \
  --agent email-phishing-agent
```

Regenerate the dataset from the upstream NAT example after changing the assembly:

```bash
uv run python plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/data/build_dataset.py
```

## Status

Structurally validated (`agent.yaml` passes `AgentConfig`, translates to a Fabric
config; `extract_iocs` unit-tested) and **live-validated for `--mode subprocess`**
(create/deploy/invoke returns a correct verdict; the adapter event graph +
LangGraph checkpointer confirm the orchestrator delegates to the subagent and
`extract_iocs` is actually called). The container (`docker`/`k8s`) package path
and the Studio Create-Example path are not yet exercised. Eval judge
weights/prompt are starters — tune per your evaluator plugin.
