---
name: nemo-build-agent
description: End-to-end NeMo Platform agent implementation from an approved agent spec. Registers and deploys the agent, generates evaluation data, runs evaluation, and signs off. Use for full spec-to-deployed-agent work, including builds from an existing legacy NAT workflow.
triggers:
  - nemo-build-agent
  - build the agent
  - create the agent
  - deploy the agent
  - scaffold the agent
  - make me an agent
  - build an agent on nemo
  - build from the agent spec
  - ship the agent
  - nemo build
  - deploy my existing NAT agent
not-for:
  - nemo-agent-config (use for focused agent.yaml authoring or migration)
  - nemo-explore (use to gather design before building)
  - nemo-spec (use to write the spec file before building)
  - nemo-try-agent (use to query an already deployed agent)
  - nemo-setup (use to install the platform first)
  - deploy-sandbox (use to deploy the built agent as a governed OpenShell sandbox)
  - generic agent framework development outside NeMo Platform
compatibility: nemo-platform >= 0.1.0; running platform; requires agents plugin; writes files under agents/; uses nemo-agents-spec-v1 by default and preserves NAT workflow YAML as a compatibility path; macOS or Linux; safe under sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
---

# NeMo Platform agent build

Build a deployable NeMo Platform agent from an approved `AGENT-SPEC.md`. Use
the Platform-owned `nemo-agents-spec-v1` `agent.yaml` path by default. Treat
NAT workflow YAML as a supported compatibility path, not the default output.

Use `nemo-agent-config` for the machine-readable config shape. Do not expose
Fabric SDK object names or raw runtime configuration to the user.

## Pre-flight

1. Run the platform probe owned by `nemo-status`. If it reports
   `PLATFORM_DOWN` or `PLATFORM_WEDGED`, route to `nemo-setup` and stop.
2. Confirm `agents/$AGENT_NAME-spec/AGENT-SPEC.md` exists. If it does not,
   route through `nemo-explore` and `nemo-spec` first.
3. Confirm the agents plugin is loaded:

   ```bash
   .venv/bin/nemo agents --help 2>&1 | grep -q "create"
   ```

4. Read the spec and extract the agent name, instructions, capabilities,
   model requirements, tools, constraints, and success criteria.
5. Confirm the canonical spec fileset exists:

   ```bash
   .venv/bin/nemo files filesets get "${AGENT_NAME}-spec" \
     --workspace "${WORKSPACE:-default}" >/dev/null 2>&1 \
     && echo "spec_fileset_ok" \
     || { echo "spec_fileset_missing - run nemo-spec first"; exit 1; }
   ```

6. Check for existing Agent entities and deployments before replacing either.
   Ask whether to reuse, update, or replace an existing deployment.

## Choose the config path

### Default: Platform-owned `agent.yaml`

For a new build, invoke `nemo-agent-config` and create:

```txt
agents/<agent-name>-spec/
  AGENT-SPEC.md
  agent.yaml
```

Start from `nemo-agent-config/references/templates/agent.yaml`. Translate the
approved spec into system instructions, a supported harness, default model,
skills, MCP servers, tools, environment paths, and telemetry. Keep every local
path relative to the directory containing `agent.yaml`.

### Compatibility: existing NAT workflow YAML

If the user supplies an existing NAT workflow YAML, do not rewrite or migrate
it automatically. Ask whether they want to:

- deploy the NAT workflow unchanged through the compatibility path; or
- migrate it best-effort to `nemo-agents-spec-v1` with `nemo-agent-config`.

Preserve the original YAML during migration. If a workflow, tool, or custom
Python component has no supported harness equivalent, keep the NAT path or
identify the need for a custom adapter. Never claim arbitrary NAT workflows
convert mechanically.

Use `references/templates/agent.yml` only when the user explicitly chooses the
legacy NAT path or needs a new NAT compatibility workflow.

## Step 1: Register and deploy

For the default path:

```bash
AGENT_NAME=<agent-name>
DEPLOYMENT_NAME="${AGENT_NAME}-deployment"

.venv/bin/nemo agents create \
  --name "$AGENT_NAME" \
  --agent-config "agents/$AGENT_NAME-spec/agent.yaml"
.venv/bin/nemo agents deploy \
  --agent "$AGENT_NAME" \
  --name "$DEPLOYMENT_NAME"
```

These commands assume a new Agent entity. If preflight found an existing Agent
or deployment, do not delete it silently. Follow the reuse or replacement choice
the user approved before creating a replacement.

`nemo agents deploy` waits for `running` by default. If the user passed
`--no-wait`, wait explicitly:

```bash
.venv/bin/nemo agents deployments wait "$DEPLOYMENT_NAME"
```

Show `agent.yaml` and the deployment result. Stop and ask whether the config,
model, harness, and instructions look right before continuing.

For an existing NAT workflow, pass its path to `--agent-config`; registration
defaults configs without `config_format` to `nat-workflow-v1`.

## Step 2: Try the deployed agent

Invoke one question from each category in the spec:

```bash
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<spec category-1 question>"
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<spec category-2 question>"
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<spec category-3 question>"
```

Display each response verbatim. Stop and ask whether to adjust the agent or
continue to evaluation.

## Step 3: Generate synthetic data

Use Data Designer for every synthetic dataset. Do not hand-author evaluation,
knowledge-base, benchmark, persona, or training data.

1. Read `agents/$AGENT_NAME-spec/AGENT-SPEC.md` and list the plausible data
   purposes: knowledge/RAG corpus, evaluation, benchmark, personas/adversarial
   inputs, training, or another user-requested purpose.
2. Wait for the user to choose. If they delegate the decision, default to an
   evaluation dataset, add a knowledge base when the spec requires retrieval,
   and add adversarial personas when it contains safety constraints.
3. Invoke `data-designer` once per selected purpose, passing the agent name,
   purpose, and spec path.
4. Require every generated config to read product context from
   `AGENT-SPEC.md`; do not duplicate that context inline.
5. Run each generated config and verify the resulting fileset exists.
6. Show 3 to 5 sample records per purpose and ask for approval.

At least one `$AGENT_NAME-eval-*` fileset must exist before evaluation.

## Step 3.5: Connect runtime data

If the generated data must be available during invocation, connect it through
the selected harness's supported skills, MCP, or tool configuration. Update
`agents/$AGENT_NAME-spec/agent.yaml` through `nemo-agent-config`, then recreate
and redeploy the Agent.

Do not invent a generic retriever field. If the selected harness cannot consume
the required data, surface that limitation and choose a supported integration,
the NAT compatibility path, or a custom adapter.

For a legacy NAT workflow, NAT-specific retrievers may be wired into its
`functions` and `workflow` blocks using the matching NAT RAG integration.

After redeployment, invoke a question that requires the data and verify the
expected tool or retrieval path was actually used.

## Step 4: Evaluate

```bash
.venv/bin/nemo evaluation benchmarks list
.venv/bin/nemo evaluation benchmark-jobs create "$AGENT_NAME-eval" \
  --input-file "agents/$AGENT_NAME.eval-job.json"
```

Use `references/templates/eval-job.json` for the job payload. Poll until the
job reaches `completed` or `failed`, then download aggregate scores. Show the
score table and compare it with the success bar in `AGENT-SPEC.md`.

## Step 5: Guardrails (optional)

If the spec defines safety or policy constraints, invoke `nemo-guardrails` for
the `nemo-agents-spec-v1` path. Apply the resulting Platform guardrail
integration without adding unsupported fields to `agent.yaml`. Recreate and
redeploy the Agent after the guardrail configuration changes.

For a legacy NAT workflow, keep the NAT compatibility behavior: add supported
guardrail `intercepts` to the NAT workflow YAML, then recreate and redeploy the
Agent. Never add NAT `intercepts` to a `nemo-agents-spec-v1` config.

For either path, test one adversarial prompt and one legitimate prompt. Report
both responses and do not continue to sign-off until the expected policy is
enforced without blocking the legitimate request.

## Step 6: Sign off

Invoke the success-criteria prompt from the spec against
`$DEPLOYMENT_NAME`. Print the verbatim response as the formal sign-off. Do not
claim success until the deployment is `running`, evaluation has completed, and
the sign-off returns an actual model response.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| Agents plugin unavailable | `plugins/nemo-agents` is not installed | Route to `nemo-setup` |
| Config validation fails | Config does not match its declared format | Use `nemo-agent-config` for `nemo-agents-spec-v1`; use NAT schema rules only for NAT YAML |
| Deployment reaches `failed` | Runtime, adapter, image, or config startup failure | Run `.venv/bin/nemo agents deployments get "$DEPLOYMENT_NAME"` and `.venv/bin/nemo agents logs "$DEPLOYMENT_NAME"` |
| Referenced file is missing | Path is outside or absent from the staged agent directory | Keep paths relative to the config and ensure the file is in the agent package |
| Adapter or binary is missing | Selected harness dependency is not installed | Install the matching adapter/runtime package or select an available harness |
| Empty response | Runtime invocation failed or the selected configuration is incomplete | Inspect deployment logs and the returned structured error |
| Eval job fails | Dataset reference or model ID is invalid | Get the benchmark job details and correct the named input |

## Hard rules

- Default new builds to `agents/$AGENT_NAME-spec/agent.yaml` with
  `config_format: nemo-agents-spec-v1`.
- Keep `AGENT-SPEC.md` as the human-readable design and `agent.yaml` as the
  machine-readable implementation config.
- Preserve legacy NAT YAML unless the user explicitly requests migration.
- Do not mix NAT-only keys such as `functions`, `llms`, `workflow`, or
  `intercepts` into `nemo-agents-spec-v1`.
- Do not put Platform `agent.yaml` fields into NAT workflow YAML.
- Use a named deployment and invoke it with `--agent-deployment`.
- Keep local artifact paths relative to the config directory.
- Recreate and redeploy after changing the persisted Agent config.
