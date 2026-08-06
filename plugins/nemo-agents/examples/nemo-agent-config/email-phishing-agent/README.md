# Tutorial: Deploy and try the email phishing agent

Deploy a Fabric (`nemo-agents-spec-v1`) agent end to end and watch it classify a
phishing email. The agent is a DeepAgents orchestrator that delegates the verdict
to a phishing sub-agent, which calls a deterministic `extract_iocs` tool.

**What you'll do:** deploy the example, send it an email, read the verdict, find
the tool call in the trace, and score it against labeled data.

**Time:** ~5 minutes.

**Prerequisites:**

- NeMo Platform running locally (see [SETUP.md](../../../../../SETUP.md)); `export NMP_BASE_URL=http://localhost:8080`.
- `export NVIDIA_API_KEY=<your key>`.
- Dependencies synced from the repo root: `uv sync --all-packages` (installs the `email-phishing-iocs` tool this agent calls).

## Step 1: Deploy the agent

```bash
nemo agents create --name email-phishing-agent \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/agent.yaml
nemo agents deploy --agent email-phishing-agent \
  --name email-phishing-agent-deployment --mode subprocess
```

The deploy command waits until the deployment reports `running` on a loopback port.

## Step 2: Classify an email

```bash
nemo agents invoke --agent-deployment email-phishing-agent-deployment \
  --input $'From: it-support@paypa1-secure.example\nSubject: Verify your account\n\nYour account is locked. Confirm your password at http://paypa1-secure.example/login'
```

The agent returns a YAML verdict with `is_likely_phishing: true` and lists the
lookalike sender domain (`paypa1-secure.example`) among its indicators.

## Step 3: Find the tool call in the trace

```bash
nemo agents logs --agent email-phishing-agent
```

The deployment's `artifacts/.../events.atof.jsonl` records an `extract_iocs` tool
call — evidence the orchestrator delegated to the sub-agent and the tool ran, not
the model guessing. With NeMo Studio Intake enabled (`VITE_FF_INTAKE_ENABLED=true`),
the same run appears under **Traces**.

## Step 4: Evaluate against labeled emails

```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/nemo-agent-config/email-phishing-agent/email-phishing-eval.yml \
  --agent email-phishing-agent
```

The judge scores each verdict against the `label` column in
`data/smaller_test.csv` and prints an accuracy score.

## Next Steps

- **Make it your own:** [CUSTOMIZE.md](CUSTOMIZE.md) — swap the tool, prompts, model, and data for your own agent.
- **Container deploys (docker/k8s):** [docs/agents/deploy-agents.mdx](../../../../../docs/agents/deploy-agents.mdx).
- **Compare with/without a tool:** the sibling [calculator-agent](../calculator-agent) example.
