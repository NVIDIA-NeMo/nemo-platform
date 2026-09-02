---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

name: nemo-build-agent
description: End-to-end NeMo Platform agent implementation from an approved Ethos. Registers and deploys the agent, generates evaluation data, runs evaluation, and signs off. Use for full Ethos-to-deployed-agent work, including builds from an existing legacy NAT workflow.
triggers:
  - nemo-build-agent
  - build the agent
  - create the agent
  - deploy the agent
  - scaffold the agent
  - make me an agent
  - build an agent on nemo
  - build from the agent Ethos
  - ship the agent
  - nemo build
  - deploy my existing NAT agent
not-for:
  - nemo-agent-config (use for focused agent.yaml authoring or migration)
  - nemo-explore (use to gather design before building)
  - nemo-ethos (use to write the Ethos before building)
  - nemo-try-agent (use to query an already deployed agent)
  - nemo-setup (use to install the platform first)
  - deploy-sandbox (use to deploy the built agent as a governed OpenShell sandbox)
  - generic agent framework development outside NeMo Platform
preconditions:
  - nemo_setup_complete
  - workspace_exists
  - provider_registered
  - agents_plugin_available
  - ethos_exists
compatibility: nemo-platform >= 0.1.0; running platform; requires agents plugin; writes files under agents/; uses nemo-agents-spec-v1 by default and preserves NAT workflow YAML as a compatibility path; macOS or Linux; safe under sandbox.
maturity: active
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write, Edit]
---

# NeMo Platform agent build

Build a deployable NeMo Platform agent from an approved `ETHOS.md`. Use
the Platform-managed `nemo-agents-spec-v1` `agent.yaml` path by default. Treat
NAT workflow YAML as a supported compatibility path, not the default output.

Use `nemo-agent-config` for the machine-readable config shape. Do not expose
Fabric SDK object names or raw runtime configuration to the user.

## Select the config path

Choose the config path before pre-flight. Set shared names for either path:

```bash
AGENT_NAME=<agent-name>
DEPLOYMENT_NAME="${AGENT_NAME}-deployment"
```

If the user supplies an existing NAT workflow YAML, ask whether they want to
deploy it unchanged or migrate it best-effort to `nemo-agents-spec-v1` with
`nemo-agent-config`. For an unchanged NAT-only run, preserve the original file
and also set:

```bash
NAT_WORKFLOW_PATH=<path-to-workflow-yaml>
```

## Pre-flight

1. Run the platform probe owned by `nemo-status`. If it reports
   `PLATFORM_DOWN` or `PLATFORM_WEDGED`, route to `nemo-setup` and stop.
2. Confirm the agents plugin is loaded:

   ```bash
   .venv/bin/nemo agents --help 2>&1 | grep -q "create"
   ```

3. Check for existing Agent entities and deployments. Ask whether to reuse or
   replace them. Follow the lifecycle branches below before create or deploy.
4. For an unchanged NAT-only run, confirm `$NAT_WORKFLOW_PATH` exists and read
   it before continuing. Do not require `ETHOS.md` or an Ethos fileset.
5. For the default Platform-managed path, confirm
   `agents/$AGENT_NAME-ethos/ETHOS.md` exists. If it does not, route through
   `nemo-explore` and `nemo-ethos` first. If
   `agents/$AGENT_NAME-spec/AGENT-SPEC.md` exists instead, route to
   `nemo-explore`.
6. Read the Ethos and extract the agent name, instructions, capabilities,
   model requirements, tools, constraints, and success criteria.
7. Confirm the canonical Ethos fileset exists:

   ```bash
   .venv/bin/nemo files filesets get "${AGENT_NAME}-ethos" \
     --workspace "${WORKSPACE:-default}" >/dev/null 2>&1 \
     && echo "ethos_fileset_ok" \
     || { echo "ethos_fileset_missing - run nemo-ethos first"; exit 1; }
   ```

Steps 5 through 7 apply only to the default Platform-managed path or an explicit
NAT migration.

### Existing-resource lifecycle

- **Reuse:** Do not run `agents create` for an existing Agent. If a deployment
  already exists, set `DEPLOYMENT_NAME` to its name, do not run `agents deploy`,
  and continue to the smoke test. If only the Agent exists, skip create and run
  only the deploy command in Step 1.
- **Replace:** Show each destructive command and require explicit confirmation
  immediately before running it. Use `--yes` only after that confirmation. If
  the resource does not exist, skip its command.

For a confirmed replacement, undeploy first:

```bash
.venv/bin/nemo agents undeploy "$DEPLOYMENT_NAME" --yes
```

Wait until this command reports that the deployment is absent before
continuing:

```bash
.venv/bin/nemo agents deployments get "$DEPLOYMENT_NAME"
```

Then show the Agent deletion command and require explicit confirmation before
running it:

```bash
.venv/bin/nemo agents delete "$AGENT_NAME" --yes
```

Verify this command reports that the Agent is absent before running the create
and deploy commands in Step 1:

```bash
.venv/bin/nemo agents get "$AGENT_NAME"
```

## Prepare the selected config

### Default: Platform-managed `agent.yaml`

For a new build, invoke `nemo-agent-config` and create:

```txt
agents/<agent-name>-ethos/
  ETHOS.md
  agent.yaml
```

Delegate authoring to `nemo-agent-config`. It selects the supported harness and
uses `nemo-model-selection` to verify the exact model against that harness's
model contract before writing the model block. Translate the approved Ethos into
system instructions, skills, MCP servers, tools, environment paths, and
telemetry. Keep every local path relative to the directory containing
`agent.yaml`.

Before registration, inspect `skills.paths`:

- If it is empty, continue with the normal deployment lifecycle below.
- If it is non-empty, verify every relative directory is inside the agent
  packaging context and contains `SKILL.md`. Package the complete bundle before
  deployment:

  ```bash
  IMAGE_TAG="${AGENT_NAME}:local"
  .venv/bin/nemo agents package \
    --agent "agents/$AGENT_NAME-ethos/agent.yaml" \
    --tag "$IMAGE_TAG"
  ```

  Use the packaged-image deploy command below. Do not use subprocess deployment
  or the default container image because those paths materialize only
  `agent.yaml` and do not stage relative skill directories.

### Compatibility: existing NAT workflow YAML

If the user selected migration, preserve the original YAML. If a workflow,
tool, or custom Python component has no supported harness equivalent, keep the
NAT path or identify the need for a custom adapter. Never claim arbitrary NAT
workflows convert mechanically.

Use `references/templates/agent.yml` only when the user explicitly chooses the
legacy NAT path or needs a new NAT compatibility workflow.

## Step 1: Register and deploy

For the default path:

For each operation retained by the selected lifecycle branch, follow the
`nemo-agent-config` confirmation requirement. Show the create command and ask
for explicit confirmation immediately before running it:

```bash
.venv/bin/nemo agents create \
  --name "$AGENT_NAME" \
  --agent-config "agents/$AGENT_NAME-ethos/agent.yaml"
```

After create succeeds, show the deploy command and ask for explicit
confirmation immediately before running it:

```bash
.venv/bin/nemo agents deploy \
  --agent "$AGENT_NAME" \
  --name "$DEPLOYMENT_NAME"
```

If `skills.paths` is non-empty, show this command instead and ask for explicit
confirmation immediately before running it:

```bash
.venv/bin/nemo agents deploy \
  --agent "$AGENT_NAME" \
  --name "$DEPLOYMENT_NAME" \
  --mode docker \
  --image "$IMAGE_TAG"
```

For Kubernetes, publish the packaged image and replace `docker` and
`$IMAGE_TAG` with `k8s` and the published image tag.

These commands assume the Agent and deployment are absent. If pre-flight found
existing resources, complete the selected lifecycle branch before running them.

`nemo agents deploy` waits for `running` by default. If the user passed
`--no-wait`, wait explicitly:

```bash
.venv/bin/nemo agents deployments wait "$DEPLOYMENT_NAME"
```

Show `agent.yaml` and the deployment result. Stop and ask whether the config,
model, harness, and instructions look right before continuing.

For an unchanged NAT workflow, registration defaults configs without
`config_format` to `nat-workflow-v1`:

Apply the same immediate confirmation requirement. Show the create command and
wait for explicit confirmation before running it:

```bash
.venv/bin/nemo agents create \
  --name "$AGENT_NAME" \
  --agent-config "$NAT_WORKFLOW_PATH"
```

After create succeeds, show the deploy command and wait for explicit
confirmation before running it:

```bash
.venv/bin/nemo agents deploy \
  --agent "$AGENT_NAME" \
  --name "$DEPLOYMENT_NAME"
```

## Step 2: Try the deployed agent

For the default path, invoke one question from each category in the Ethos
`Scope` section (`Categories`). Do not invent a separate category heading. For
an unchanged NAT-only run without an Ethos, use representative questions from the
workflow and the user's stated requirements:

```bash
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<smoke-test question-1>"
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<smoke-test question-2>"
.venv/bin/nemo agents invoke \
  --agent-deployment "$DEPLOYMENT_NAME" \
  --input "<smoke-test question-3>"
```

Display each response verbatim. Stop and ask whether to adjust the agent or
continue to evaluation.

Before Step 3, branch explicitly:

1. For an unchanged NAT-only run without `ETHOS.md`, stop after the smoke
   test. Do not execute Steps 3–5 and do not require an evaluation fileset.
2. Continue into the Ethos-driven purpose selection and Data Designer flow only
   when the user requests it and `agents/$AGENT_NAME-ethos/ETHOS.md` exists.
   If the user requests evaluation but the Ethos is absent, create and confirm
   the Ethos first; do not continue to Step 3 yet.

## Step 3: Generate synthetic data

Use Data Designer for every synthetic dataset. Do not hand-author evaluation,
knowledge-base, benchmark, persona, or training data.

1. Always select evaluation as a required data purpose. Read
   `agents/$AGENT_NAME-ethos/ETHOS.md` and list any additional plausible
   purposes: knowledge/RAG corpus, benchmark, personas/adversarial inputs,
   training, or another user-requested purpose.
2. Wait for the user to choose any additional purposes. Evaluation cannot be
   omitted. If they delegate the decision, add a knowledge base when the Ethos
   requires retrieval and adversarial personas when it contains safety
   constraints.
3. Invoke `data-designer` once per selected purpose, passing the agent name,
   purpose, and Ethos path.
4. Require every generated config to read product context from
   `ETHOS.md`; do not duplicate that context inline.
5. Run each generated config. For evaluation, validate the generated records,
   verify the resulting fileset exists, and record its exact dataset reference
   as `EVAL_DATASET_REF`.
6. Show 3 to 5 sample records per purpose and ask for approval.

A validated `$AGENT_NAME-eval-*` fileset and its exact `EVAL_DATASET_REF` must
exist before evaluation proceeds.

## Step 3.5: Connect runtime data

If the generated data must be available during invocation, connect it through
the selected harness's supported skills, MCP, or tool configuration. Update
`agents/$AGENT_NAME-ethos/agent.yaml` through `nemo-agent-config`, then follow the
confirmed replacement branch before creating and deploying the Agent again.

Do not invent a generic retriever field. If the selected harness cannot consume
the required data, surface that limitation and choose a supported integration,
the NAT compatibility path, or a custom adapter.

For a legacy NAT workflow, NAT-specific retrievers may be wired into its
`functions` and `workflow` blocks using the matching NAT RAG integration.

After the replacement deployment, invoke a question that requires the data and
verify the expected tool or retrieval path was actually used.

## Step 4: Evaluate

Select the actual Platform model reference as `EVAL_MODEL`. Create
`agents/$AGENT_NAME.eval-job.json` from `references/templates/eval-job.json` and
replace every placeholder. Its `model` must equal `EVAL_MODEL`, and its
`dataset` must equal the recorded `EVAL_DATASET_REF` from Step 3.

Validate the rendered file before creating the benchmark job:

```bash
.venv/bin/python -m json.tool "agents/$AGENT_NAME.eval-job.json" >/dev/null
if grep -Eq '<[^>]+>' "agents/$AGENT_NAME.eval-job.json"; then
  echo "eval job still contains template placeholders" >&2
  exit 1
fi
```

Also read the validated payload back and confirm its `model` and `dataset`
values match `EVAL_MODEL` and `EVAL_DATASET_REF`. Do not invoke
`benchmark-jobs create` if JSON validation, model validation, dataset
validation, or fileset validation fails.

After all validation succeeds:

```bash
.venv/bin/nemo evaluation benchmarks list
.venv/bin/nemo evaluation benchmark-jobs create "$AGENT_NAME-eval" \
  --input-file "agents/$AGENT_NAME.eval-job.json"
```

Poll until the job reaches `completed` or `failed`, then download aggregate
scores. Show the score table and compare it with the success bar in
`ETHOS.md`.

```bash
for i in $(seq 1 24); do
  status=$(.venv/bin/nemo evaluation benchmark-jobs get-status "$AGENT_NAME-eval" 2>/dev/null)
  echo "$status"
  echo "$status" | grep -qE "completed|failed" && break
  sleep 10
done

.venv/bin/nemo evaluation benchmark-jobs results aggregate-scores download \
  "$AGENT_NAME-eval"
```

## Step 5: Guardrails (optional)

For `nemo-agents-spec-v1`, `AgentConfig` has no guardrail field and the current
skills do not define a supported composition between an Agent and an IGW
guardrailed VirtualModel. Do not add guardrail fields to `agent.yaml` or claim
that guardrails are attached. If the Ethos requires guardrails, report this as an
unmet requirement and stop before sign-off. `nemo-guardrails` may be used to
configure IGW VirtualModel middleware as a separate workflow, but do not treat
it as integrated with the Agent until its model routing has been explicitly
configured and validated.

For a legacy NAT workflow, keep the NAT compatibility behavior: add supported
guardrail `intercepts` to the NAT workflow YAML, then follow the confirmed
replacement branch before creating and deploying it again. Never add NAT
`intercepts` to a `nemo-agents-spec-v1` config.

For the NAT path, test one adversarial prompt and one legitimate prompt. Report
both responses and do not continue to sign-off until the expected policy is
enforced without blocking the legitimate request.

## Step 6: Sign off

Invoke the success-criteria prompt from the Ethos against
`$DEPLOYMENT_NAME`. Print the verbatim response as the formal sign-off. Do not
claim success until the deployment is `running`, evaluation has completed, and
the sign-off returns an actual model response.

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| Agents plugin unavailable | `plugins/nemo-agents` is not installed | Route to `nemo-setup` |
| Config validation fails | Config does not match its declared format | Use `nemo-agent-config` for `nemo-agents-spec-v1`; use NAT schema rules only for NAT YAML |
| Deployment reaches `failed` | Runtime, adapter, image, or config startup failure | Run `.venv/bin/nemo agents deployments get "$DEPLOYMENT_NAME"` and `.venv/bin/nemo agents logs "$DEPLOYMENT_NAME"` |
| Referenced file is missing | Path is outside or absent from the staged agent directory | Keep paths relative to the config and package the complete agent bundle into the deployed image |
| Adapter or binary is missing | Selected harness dependency is not installed | Install the matching adapter/runtime package or select an available harness |
| Empty response | Runtime invocation failed or the selected configuration is incomplete | Inspect deployment logs and the returned structured error |
| Eval job fails | Dataset reference or model ID is invalid | Get the benchmark job details and correct the named input |

## Hard rules

- Default new builds to `agents/$AGENT_NAME-ethos/agent.yaml` with
  `config_format: nemo-agents-spec-v1`.
- Keep `ETHOS.md` as the human-readable design and `agent.yaml` as the
  machine-readable implementation config.
- Preserve legacy NAT YAML unless the user explicitly requests migration.
- Do not mix NAT-only keys such as `functions`, `llms`, `workflow`, or
  `intercepts` into `nemo-agents-spec-v1`.
- Do not put Platform `agent.yaml` fields into NAT workflow YAML.
- Use a named deployment and invoke it with `--agent-deployment`.
- Keep local artifact paths relative to the config directory.
- After changing persisted Agent config, use the confirmed replacement branch
  before creating and deploying it again.
