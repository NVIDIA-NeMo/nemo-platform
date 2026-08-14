# Dataset-Driven evaluation — Email Security Triage

Every row of `dataset.jsonl` is scored by the same metric set. Use this shape when the inputs are
homogeneous and the interesting variable is coverage, not the kind of task.

## The dataset

`dataset.jsonl` is a 6-row demo subset (3 phishing, 3 benign), each with `subject`, `sender`,
`body`, and `label`. `dataset-full.jsonl` sits beside it with the full 40 rows (22 phishing,
18 benign) for real measurement — swap it in by renaming, or point a fileset at it directly.

The subset is small on purpose. A phishing email with a link costs the agent roughly 66s and 50k
prompt tokens, because the orchestrator delegates to several sub-agents and re-sends the message to
each; a link-free benign email costs about 10s. 40 rows therefore runs for tens of minutes, which is
the wrong shape for a demo. The subset favours link-free rows and keeps one near-miss pair — a
phishing and a benign email that share the subject "Password Expiration Notice" — since
discriminating those is the point of the sample.

`prompt_template` assembles rows into the RFC-822 message the agent expects:

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

The full set is adversarial by design: several benign emails carry the same subject lines as
phishing ones, so a model that keys on subject wording scores badly. Expect well under 100%.

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
