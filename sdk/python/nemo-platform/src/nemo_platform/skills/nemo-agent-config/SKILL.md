---
name: nemo-agent-config
description: Author and validate Platform-owned NeMo Agents agent.yaml files using the nemo-agents-spec-v1 format. Use when the user wants to create, edit, validate, or adapt an agent.yaml file, choose a supported harness, add instructions, skills, MCP servers, tools, environment, or telemetry.
triggers:
  - write agent.yaml
  - create agent.yaml
  - edit agent.yaml
  - validate agent.yaml
  - configure a harness
  - configure agent harness
  - nemo-agents-spec-v1
  - platform agent config
  - adapt agent.yaml
  - convert NAT workflow YAML
  - migrate NAT workflow
  - convert agent.yml to agent.yaml
  - NeMo agent.yaml config
not-for:
  - nemo-build-agent (use for full spec-to-deployed-agent build flows)
  - nemo-explore (use to design what the agent should do before writing config)
  - nemo-spec (use to write AGENT-SPEC.md before implementation)
  - nemo-model-selection (use when the user only wants model recommendation)
  - generic YAML editing unrelated to NeMo Platform agents
compatibility: nemo-platform >= 0.1.0; writes or edits agents/<name>-spec/agent.yaml; validates through nemo agents create; supports nemo-agents-spec-v1 configs; safe under sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Read, Write, Edit, Bash]
---

# NeMo Platform agent config

Create or edit the Platform-owned `agent.yaml` for a NeMo Agent. This skill
owns the machine-readable config shape for `nemo-agents-spec-v1`; `nemo-build-agent`
owns the full build/deploy/eval workflow.

Use product-facing Platform language. Do not ask users to write raw Fabric SDK
configuration. Fabric is an implementation dependency behind the Platform-owned
agent config.

## Storage model

The local config lives next to the human-readable agent spec:

```txt
agents/<agent-name>-spec/
  AGENT-SPEC.md
  agent.yaml
```

The platform stores the parsed `agent.yaml` contents in the `Agent.config`
payload with:

```yaml
config_format: nemo-agents-spec-v1
```

The canonical remote config location is derivable from workspace and agent name:
`<workspace>/<agent-name>-spec#agent.yaml`. Do not invent a separate ref field.

## What you do

1. Confirm the agent name and config path. Default to
   `agents/<agent-name>-spec/agent.yaml`.
2. Start from `references/templates/agent.yaml` unless the user is editing an
   existing file.
3. Select one supported harness:
   - `codex`
   - `hermes`
   - `deepagents`
   - `claude`
4. Configure `models.default` and add a harness-local `model` override only when
   that harness should use a different provider, model, credential env var, or
   base URL.
5. Add system instructions under `instructions.system.content`.
6. Add optional skills, MCP servers, blocked tools, environment directories, and
   telemetry using only fields in the template.
7. Keep all local file paths relative to the directory containing `agent.yaml`.
8. Validate by running `nemo agents create` against the config.

## Migrating from legacy NAT workflow YAML

If the user has an existing NAT workflow YAML and wants the new Platform-owned
`agent.yaml` format, treat the migration as best-effort authoring. Do not
overwrite the original NAT YAML unless the user explicitly asks.

Map only fields with a clear Platform equivalent:

| NAT workflow concept | Platform `agent.yaml` target |
|---|---|
| LLM/provider/model block | `models.default` or a harness-local `model` |
| System prompt or workflow prompt | `instructions.system.content` |
| Workflow/tool loop choice | `default_harness` plus `harnesses.<name>.kind` |
| Tool/function references | `skills.paths`, `mcp.servers`, `tools.blocked`, or harness settings when clearly supported |
| Tracing or telemetry settings | `telemetry` |

If behavior does not map cleanly, say so directly and choose one:

- Keep the agent on the NAT compatibility path.
- Preserve the original NAT YAML and create a partial `agent.yaml` starter for
  manual completion.
- Mark it as requiring a custom adapter or a manual harness-specific migration.

Never claim a mechanical one-to-one conversion for arbitrary NAT workflows.

## Config shape

Use this structure. Keep unknown fields out of the YAML; the Platform validator
rejects unsupported fields instead of passing arbitrary execution config through.

```yaml
config_format: nemo-agents-spec-v1
name: <agent-name>
description: <short description>

instructions:
  system:
    content: <system instructions>

default_harness: codex

harnesses:
  codex:
    kind: codex
    settings:
      sandbox: workspace-write
      reasoning_effort: high

models:
  default:
    provider: nvidia
    model: nvidia/nemotron-3-nano-30b-a3b
    api_key_env: NVIDIA_API_KEY

skills:
  paths: []

mcp:
  servers: {}

tools:
  blocked: []

environment:
  workspace: ./workspace
  artifacts: ./artifacts

telemetry:
  enabled: false
  provider: relay
  output_dir: ./artifacts/relay
  project: <agent-name>
```

### Harness overrides

Use a harness-local model only when that harness should override the default.

```yaml
harnesses:
  hermes:
    kind: hermes
    model:
      provider: nvidia
      model: nvidia/nemotron-3-nano-30b-a3b
      api_key_env: NVIDIA_API_KEY
      base_url: https://integrate.api.nvidia.com/v1
      temperature: 0.0
    settings:
      max_tokens: 512
      reasoning_config:
        effort: none
```

If `base_url` is needed, put it directly in the model block, not under
`settings`.

Before selecting `codex` or making it the default harness, use
`nemo-model-selection` to verify that the selected provider endpoint supports
the OpenAI Responses API. Do not infer Codex compatibility from a model merely
appearing in the Platform model list. NVIDIA models may be used when Platform
routes the exact model through an Inference Gateway endpoint that supports
`/responses`; endpoints that expose only chat completions are not compatible.

## Validate and register

Before registering, validate the YAML shape with the Platform create path.
Immediately before running `nemo agents create`, show the command to the user,
ask for explicit confirmation, and wait for approval.

```bash
.venv/bin/nemo agents create \
  --name "$AGENT_NAME" \
  --agent-config "agents/$AGENT_NAME-spec/agent.yaml"
```

If validation fails, fix the named field in `agent.yaml` and retry. Do not
silence validation errors by moving unknown fields into `settings`.

## Deploy and invoke

After create succeeds, show the `nemo agents deploy` command to the user, ask
for explicit confirmation, and wait for approval before running it.

```bash
.venv/bin/nemo agents deploy \
  --agent "$AGENT_NAME" \
  --name "$AGENT_NAME-deployment"
```

After deployment begins, wait for it and invoke it without another confirmation:

```bash
.venv/bin/nemo agents deployments wait \
  --agent "$AGENT_NAME"

.venv/bin/nemo agents invoke \
  --agent-deployment "$AGENT_NAME-deployment" \
  --input "<test prompt>"
```

For local one-shot validation without registering an Agent entity, use this
only when the selected model already has a directly usable provider endpoint
and credentials. Platform IGW normalization is applied by the registered
deployment path, not this local path:

```bash
.venv/bin/nemo agents invoke \
  --agent-config "agents/$AGENT_NAME-spec/agent.yaml" \
  --input "<test prompt>"
```

For a local persistent server, bind to loopback by default. Use an externally
accessible host only when the user explicitly asks to expose the server:

```bash
.venv/bin/nemo agents run \
  --agent-config "agents/$AGENT_NAME-spec/agent.yaml" \
  --host 127.0.0.1 \
  --port 8080
```

## If validation fails

| Symptom | Cause | Recovery |
|---|---|---|
| `root must be a YAML mapping` | Empty file or list/scalar at the root | Replace with the template shape |
| `extra fields not permitted` | Unknown Platform config field | Remove it or map it into a supported field |
| `default_harness must reference one of harnesses` | `default_harness` does not match a key under `harnesses` | Rename one side so they match |
| `Unsupported harness kind` | Harness kind is not supported by the Platform translator | Pick `codex`, `hermes`, `deepagents`, or `claude` |
| Local file path missing in deployment | Referenced prompts, skills, or assets were not staged | Keep paths relative and ensure referenced files are present in the agent package or fileset before deployment |
| Adapter import or binary missing | Selected harness dependency is not installed in the runtime | Install the selected adapter/runtime dependency or choose a harness already available |

## Hard rules

- Keep `config_format: nemo-agents-spec-v1`.
- Keep paths relative to the `agent.yaml` directory.
- Put system instructions under `instructions.system.content`.
- Do not use `prompts` for the default path; top-level prompts are not translated yet.
- Do not create profile files. Profiles are not the Platform authoring contract.
- Do not expose Fabric SDK object names as user-authored YAML fields.
- Do not emit arbitrary adapter settings unless the selected harness documents them.

## Gotchas

- **Default model vs harness model.** A harness-local `model` always wins over
  `models.default`.
- **Registration validates and normalizes.** `nemo agents create` is the
  user-facing validation command.
- **`agent.yaml` is the implementation config, not the design spec.**
  `AGENT-SPEC.md` explains what the agent should do; `agent.yaml` tells the
  Platform how to run it.
- **NAT workflow YAML is a compatibility path.** If the user explicitly asks
  for legacy NAT, route to `nemo-build-agent` and use its NAT template.
