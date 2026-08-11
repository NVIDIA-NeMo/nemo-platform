# Tutorial: Deploy and try the Email Security Triage agent

Deploy a Fabric (`nemo-agents-spec-v1`) agent end to end and watch it classify a
phishing email. The agent is a DeepAgents orchestrator that calls a deterministic
`extract_iocs` tool, fans out to specialist sub-agents (brand impersonation,
attack category, SMTP header auth), and delegates the final verdict to a phishing
sub-agent.

**What you'll do:** deploy the example, send it an email, read the verdict, watch
a specialist fire, find the steps in the trace, and score it against labeled data.

**Time:** ~5 minutes.

**Prerequisites:**

- NeMo Platform running locally (see [SETUP.md](../../../../../SETUP.md)); `export NMP_BASE_URL=http://localhost:8080`.
- `export NVIDIA_API_KEY=<your key>`.
- Dependencies synced from the repo root: `uv sync --all-packages` (installs the `email-security-triage-iocs` tool this agent calls).

## Step 1: Deploy the agent

```bash
nemo agents create --name email-security-triage \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-security-triage/agent.yaml
nemo agents deploy --agent email-security-triage \
  --name email-security-triage-deployment --mode subprocess
```

The deploy command waits until the deployment reports `running` on a loopback port.

## Step 2: Classify an email

```bash
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input $'From: it-support@paypa1-secure.example\nSubject: Verify your account\n\nYour account is locked. Confirm your password at http://paypa1-secure.example/login'
```

The agent returns a YAML verdict with `is_likely_phishing: true`, listing the
lookalike sender domain (`paypa1-secure.example`) among its indicators.
`phishing-analyzer` owns the verdict and emits every field, including
`attack_type` (e.g. `credential`) and `impersonated_brand` (e.g. `paypal`) — it
fills those from the `attack-attributor` and `url-brand-analyst` findings, which
are advisory: it can override them, or supply a value itself when a specialist is
silent.

## Step 3: Watch the header specialist fire

`header-auth-analyst` reads SMTP authentication results, so it only runs when the
email actually carries them. Send one that does:

```bash
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input $'Received: from mail.evil.example (203.0.113.9)\nFrom: security@paypal.com\nReturn-Path: bounce@evil.example\nAuthentication-Results: mx.example.com; spf=fail smtp.mailfrom=evil.example; dkim=fail header.d=paypal.com; dmarc=fail header.from=paypal.com\nSubject: Unusual sign-in\n\nReview the sign-in at http://paypal-secure-review.example/verify'
```

The authentication results fail across the board — critically `dmarc=fail` on
`header.from=paypal.com`, the check tied to the visible `From:` domain, so the
message isn't authorized to claim `paypal.com`. `header-auth-analyst` names the
failed mechanism, and it surfaces among the indicators.

The labeled dataset in Step 5 carries no SMTP headers, so this specialist stays
idle there. That is deliberate: synthesizing auth results per row would put the
`phishing`/`benign` label into the input and inflate the score.

## Step 4: Find the steps in the trace

```bash
nemo agents logs --agent email-security-triage
```

The deployment's `artifacts/.../events.atof.jsonl` records the `extract_iocs` tool
call and a task for each specialist the orchestrator consulted — evidence the tool
ran and the specialists were invoked, not that the model guessed. Which specialists
appear depends on the input: `url-brand-analyst` and `attack-attributor` run on the
Step 2 email, while `header-auth-analyst` appears only for header-bearing input
like Step 3's. With NeMo Studio Intake enabled (`VITE_FF_INTAKE_ENABLED=true`), the
same run appears under **Traces**, one span per step.

## Step 5: Evaluate against labeled emails

```bash
nemo agents evaluate run \
  --eval-config plugins/nemo-agents/examples/nemo-agent-config/email-security-triage/email-security-triage-eval.yml \
  --agent email-security-triage
```

The judge scores each verdict against the `label` column in
`data/smaller_test.csv` and prints an accuracy score.

## Next Steps

- **Make it your own:** [CUSTOMIZE.md](CUSTOMIZE.md) — swap the tool, prompts, specialists, model, and data for your own agent.
- **Container deploys (docker/k8s):** [docs/agents/deploy-agents.mdx](../../../../../docs/agents/deploy-agents.mdx).
- **Compare with/without a tool:** the sibling [calculator-agent](../calculator-agent) example.
