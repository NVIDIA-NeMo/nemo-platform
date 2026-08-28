<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Tutorial: Deploy and try the Email Security Triage agent

Deploy a Fabric (`nemo-agents-spec-v1`) agent end to end and watch it route an
analyst's question to the right capability. The agent is a single-turn router: it
picks one of four capabilities — general review, phishing/benign triage, thread
injection-point tracing, and drafting a staff warning — and answers as that
capability, in one generation, with no tools and no sub-agents.

**What you'll do:** deploy the example, ask it a question, watch the answer change
shape when the question changes, find the run in the trace, and score it against
labeled data.

**Time:** ~5 minutes.

**Prerequisites:**

- NeMo Platform running locally (see [SETUP.md](../../../../../SETUP.md)); `export NMP_BASE_URL=http://localhost:8080`.
- `export NVIDIA_API_KEY=<your key>`.
- Dependencies synced from the repo root: `uv sync --all-packages`.

## Step 1: Deploy the agent

```bash
nemo agents create --name email-security-triage \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/email-security-triage/agent.yaml
nemo agents deploy --agent email-security-triage \
  --name email-security-triage-deployment --mode subprocess
```

The deploy command waits until the deployment reports `running` on a loopback port.

## Step 2: Ask whether a message is legitimate

```bash
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input '{"user_message": "is this legit?", "emails": ["Subject: Verify your account\nFrom: it-support@paypa1-secure.example\n\nYour account is locked. Confirm your password at http://paypa1-secure.example/login"]}'
```

The first line is exactly `phishing` — one lowercase word, alone. The reasoning
follows on the lines after it, naming the lookalike sender domain
(`paypa1-secure.example`) and the credential request.

That answer-first shape is the point: every capability puts a bare answer on line
one and explains after, so a metric can read the result without an LLM. It is also
what makes routing measurable — see Step 3.

Input is a JSON object with two keys. `user_message` is what the analyst typed
(`""` when they typed nothing); `emails` is what they selected. Plain email text
works too and is treated as the selected message.

## Step 3: Watch the question change the answer's shape

Same agent, same email, different question — a different capability answers, with a
different contract on line one.

```bash
# no question -> general review: line 1 is ANALYSIS, then a block per message
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input '{"user_message": "", "emails": ["Subject: Verify your account\nFrom: it-support@paypa1-secure.example\n\nConfirm your password at http://paypa1-secure.example/login"]}'

# "where did this go bad?" -> thread tracing: line 1 is a bare integer
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input '{"user_message": "where did this thread go bad?", "emails": ["Subject: Kickoff notes\nFrom: dana@acme.com\n\nNotes attached.", "Subject: RE: Kickoff notes\nFrom: sam@acme.com\n\nLooks right to me.", "Subject: RE: Kickoff notes\nFrom: dana@acme-corp-mail.net\n\nWire the deposit via http://acme-billing-update.example.com today."]}'

# "write a warning" -> drafting: line 1 is prose, no verdict word
nemo agents invoke --agent-deployment email-security-triage-deployment \
  --input '{"user_message": "write a warning for the team", "emails": ["Subject: DocuSign: contract awaiting signature\nFrom: no-reply@docusign-secure-files.com\n\nSign at http://docusign-secure-files.com/sign before it expires."]}'
```

Four capabilities, four distinct first lines: `phishing`/`benign`, `ANALYSIS`, a
bare integer, and prose. Because they cannot be confused for each other, a
deterministic check on line one proves _which capability ran_ — that is how the
Studio eval samples assert routing without inspecting tool calls.

The general review also reports an `IOCS:` field per message, listing the URLs and
domains it found. The prompt produces those; this agent calls no tools. To wire a
deterministic extractor in instead, see [CUSTOMIZE.md](CUSTOMIZE.md).

## Step 4: Find the run in the trace

```bash
nemo agents logs --agent email-security-triage
```

The deployment's `artifacts/.../events.atof.jsonl` records the invocation. With
NeMo Studio Intake enabled (`VITE_FF_INTAKE_ENABLED=true`), the same run appears
under **Traces**.

Expect **one** LLM call per invocation. There is no per-capability span, because
there is no per-capability call — the capability is a section of one prompt, not a
separate step. That is the trade this design makes:
it gives up step-level traces and buys back cost, plus a first line that means what
it says.

## Step 5: Evaluate against labeled emails

This example ships two eval configs, both in the evaluator SDK's format:

| File                             | Shape                                                 | Scores                          |
| -------------------------------- | ----------------------------------------------------- | ------------------------------- |
| `eval-config.dataset-driven.yml` | one metric set over every row of `dataset.jsonl`      | verdict accuracy + routing      |
| `eval-config.task-driven.json`   | 10 tasks in 5 families, each carrying its own metrics | all four capabilities + routing |

One is YAML and one is JSON on purpose: **both formats are accepted everywhere a
config is read.** Studio's upload and the CLI's `--spec-file` sniff the content
rather than the extension, so use whichever reads better — YAML suits configs with
multi-line prompts, JSON suits generated ones.

Both ship **without** `target`, `params`, or a resolved `dataset` — those are
per-run, and Studio's Run Evaluation flow injects them. From the CLI you supply
them yourself.

Upload the dataset once, so the config can reference it:

```bash
nemo files filesets create esec-eval-data
nemo files upload plugins/nemo-agents/examples/nemo-agent-config/email-security-triage/dataset.jsonl esec-eval-data
```

Then build a run spec from the shipped config, adding the three per-run fields:

```bash
python3 - <<'EOF' > /tmp/esec-eval-spec.json
import json, yaml
spec = yaml.safe_load(open("plugins/nemo-agents/examples/nemo-agent-config/email-security-triage/eval-config.dataset-driven.yml"))
agent = "email-security-triage"
spec["dataset"] = "default/esec-eval-data#dataset.jsonl"
spec["target"] = {
    "format": "generic",
    "url": f"http://localhost:8080/apis/agents/v2/workspaces/default/agents/{agent}/-/v1/chat/completions",
    "name": agent,
    "body": {"model": agent, "messages": [{"role": "user", "content": "{{ prompt }}"}], "stream": False},
    "response_path": "$.choices[0].message.content",
    "stream": False,
}
spec["params"] = {"parallelism": 1, "request_timeout": 300, "max_retries": 3, "ignore_request_failure": True}
print(json.dumps(spec, indent=2))
EOF

nemo evaluator evaluate run --spec-file /tmp/esec-eval-spec.json
```

Note this is `nemo evaluator evaluate run`, not `nemo agents evaluate run` — the
latter takes a NAT-format eval YAML, and these configs are evaluator SDK specs.
The task-driven config runs the same way through
`nemo evaluator agent-evaluate run`, whose spec wraps its tasks in an `agent`
target instead.

`prompt_template` renders each row into `Is this legit?` plus the message, so
every row routes to the triage capability and answers with a bare `phishing` or
`benign` on line one. Two metrics score that:

- `llm-judge.accuracy` — does line one match the row's `label`?
- `string-check` — is line one a verdict word at all? This is the **routing**
  assertion: it holds at 1.0 whenever the right capability answered, regardless of
  whether the verdict was right.

Read the two together. Accuracy with headroom while routing holds means the misses
are judgement calls; both collapsing together means the agent answered as the wrong
capability. That is the distinction the routing check exists to make.

`parallelism: 1` above matches what Studio submits, so the two paths produce
comparable numbers; raise it to shorten the run.

## Next Steps

- **Make it your own:** [CUSTOMIZE.md](CUSTOMIZE.md) — swap the capabilities, model, and data for your own agent.
- **Container deploys (docker/k8s):** [docs/agents/deploy-agents.mdx](../../../../../docs/agents/deploy-agents.mdx).
- **Compare with a tool-calling agent:** the sibling [calculator-agent](../calculator-agent) example.
