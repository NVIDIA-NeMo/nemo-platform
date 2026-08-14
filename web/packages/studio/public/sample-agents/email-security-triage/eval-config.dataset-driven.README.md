# Dataset-Driven evaluation — Email Security Triage

Every row of `dataset.jsonl` is scored by the same metric set. Use this shape when the inputs are
homogeneous and the interesting variable is coverage, not the kind of task.

## The dataset

40 rows (22 phishing, 18 benign), each with `subject`, `sender`, `body`, and `label`.
`prompt_template` assembles them into the RFC-822 message the agent expects:

```jinja
From: {{ item.sender }}
Subject: {{ item.subject }}

{{ item.body }}
```

The `From:` line is deliberate — the sender domain is a top phishing signal and is what the agent's
`extract_iocs` tool harvests. Dropping it measurably weakens the agent.

`label` is the only ground truth here. The rows are shared with the email-security-analyst sample:
the dataset carries inputs and labels only, so it is agent-agnostic — the YAML verdict contract
lives entirely in the metrics below. Add rows by appending to `dataset.jsonl`.

## How the verdict is read

The agent answers with a YAML block whose `is_likely_phishing` key carries the verdict. Metrics
read that key out of the body with `contains`, because the model usually wraps the block in a ```
fence despite being asked not to — anything anchored to the start of the response scores 0 for
every row.

## Metrics

- `string-check` — deterministic. Its expected value is rendered per row
  (`is_likely_phishing: {% if item.label == 'phishing' %}true{% else %}false{% endif %}`), so it
  needs no judge model and scores even when the judge is unreachable.
- `llm-judge` — grades the verdict and whether `attack_type` is a sensible label, as two `scores`
  on one metric.
