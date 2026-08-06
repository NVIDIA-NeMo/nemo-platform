# Email Phishing Analyzer — Fabric example (`nemo-agents-spec-v1`)

A Platform-native port of the email-phishing analyzer. Unlike the NAT ReAct
example (`../email-phishing-analyzer`), the classification does **not** hide
behind an opaque MCP server. It runs as a Fabric **deepagents orchestrator** that
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
  `harness_native` stdio MCP server.
- **`src/email_phishing_fabric/`** — the `extract_iocs` MCP tool. Pure-regex
  URL/domain extraction (ported from the email-security-analyst example), served
  over stdio by the `email-phishing-iocs-mcp` console script.
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
installed `email-phishing-iocs-mcp` into the repo `.venv`. The subprocess
deployment runs from that same venv (`sys.executable`) and inherits its `PATH`,
so Fabric can spawn the tool — no extra install and no image needed:

```bash
nemo agents create  --name email-phishing-fabric \
  --agent-config plugins/nemo-agents/examples/email-phishing-fabric/agent.yaml
nemo agents deploy  --agent email-phishing-fabric --name email-phishing-fabric-deployment
nemo agents invoke  --agent-deployment email-phishing-fabric-deployment \
  --input "From: it-support@paypa1-secure.example
Subject: Verify your account

Your account is locked. Confirm your password at http://paypa1-secure.example/login"
```

### Container (`--mode docker` / `k8s`)

A deployment container does **not** have this example installed, so a local
`uv pip install` cannot reach it. Bake the package into an image with
`nemo agents package` — project mode (`--pyproject`) runs `uv pip install .`,
which provides the `email-phishing-iocs-mcp` console script — then deploy that
image:

```bash
nemo agents package \
  --agent plugins/nemo-agents/examples/email-phishing-fabric/agent.yaml \
  --pyproject plugins/nemo-agents/examples/email-phishing-fabric/pyproject.toml \
  --tag email-phishing-fabric:local

nemo agents create  --name email-phishing-fabric \
  --agent-config plugins/nemo-agents/examples/email-phishing-fabric/agent.yaml
nemo agents deploy \
  --agent email-phishing-fabric \
  --name email-phishing-fabric-deployment \
  --mode docker \
  --image email-phishing-fabric:local
```

For Kubernetes, publish the image
(`nemo agents package ... --publish --registry <registry>`) and pass the
published image to `nemo agents deploy --mode k8s --image <image>`.

Evaluate against the sender-inclusive dataset:

```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/email-phishing-fabric/email-phishing-eval.yml \
  --agent email-phishing-fabric
```

## Status

Structurally validated: `agent.yaml` passes `AgentConfig` (`nemo-agents-spec-v1`)
and translates to a typed Fabric config; `extract_iocs` is unit-tested. A live
create/deploy/invoke against a running Platform (with `NVIDIA_API_KEY`) is the
next step and is not exercised here. Eval judge weights/prompt are starters —
tune per your evaluator plugin.
