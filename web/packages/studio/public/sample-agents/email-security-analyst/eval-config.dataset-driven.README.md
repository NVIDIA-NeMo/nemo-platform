# Dataset-driven evaluation — Email Security Analyst

This fileset holds the **dataset-driven** eval config seeded from the built-in Email
Security Analyst sample, plus the dataset and this note. It is yours to edit; nothing
regenerates it.

Dataset-driven means **one metric set scores every row** of a fixed dataset. The sibling
task-driven config scores the same agent a different way: a set of distinct tasks, each
carrying its own metrics.

## What is being evaluated

One question, asked 40 times over 40 different emails: can the agent tell a phishing
message from a legitimate one?

This measures a single capability in depth, where the task-driven suite measures breadth.
Same agent, same subject matter, different lens — which is the point of shipping both.

## The dataset

`dataset.jsonl` — 40 rows, balanced 20 phishing / 20 benign. Each row:

```json
{ "subject": "...", "sender": "...", "body": "...", "label": "phishing" }
```

`label` is the ground truth and is never shown to the agent.

The rows are deliberately contestable, not textbook. Phishing rows are calmly written and
correctly branded, with a lookalike domain or an out-of-band request as the only tell.
Benign rows look alarming on the surface — invoices, password resets, wire transfers — but
come from consistent senders and ask for nothing. Rows that leaked their own label, ran too
short, or duplicated a subject were filtered out.

## How a row reaches the agent

`prompt_template` renders each row into a question plus the message:

```text
Is this legit?

Subject: {{ item.subject }}
From: {{ item.sender }}

{{ item.body }}
```

That question is what routes the agent to its triage capability, which answers with a bare
`phishing` or `benign` on the first line and its reasoning after.

## The metric

| Metric      | Output   | Range | Checks                                     |
| ----------- | -------- | ----- | ------------------------------------------ |
| `llm-judge` | accuracy | 0–1   | First line of the response matches `label` |

The judge reads the **first line**, not the last. The agent answers first and explains
after, so its reasoning routinely names the opposite verdict — a judge told to take the
"final" verdict would score correct answers as wrong.

## Reading the results

Expect a mid-range score, not a perfect one; the dataset was built to leave headroom. A
recent baseline run scored **0.63** with a clear pattern: of 14 errors, 12 were **false
positives** — benign mail called phishing. The agent is a security assistant told to hunt
social-engineering signals, so it leans cautious. That asymmetry is more interesting than
the headline number and is worth checking on your own runs.

A near-zero score means something mechanical, not a collapsed agent: most likely the judge
reading the wrong line, or the agent's tool missing from the workflow's `return_direct`, so
a second generation rewrote the answer away from the first-line contract.

## Editing this config

`dataset` in this fileset already points at the copy of `dataset.jsonl` sitting beside it —
it is rewritten at seed time so the config and its data travel together. The published
template instead carries a placeholder, `<workspace>/<fileset>#dataset.jsonl`, because no
such fileset exists in a fresh workspace; anything running that template directly, rather
than through the Run Evaluation flow, must set a real reference first.

If you point it elsewhere, keep the four field names — the `prompt_template` and the judge
both reference them.

Metric templates get string operations only; there is no JSON parsing, which is why the
answer is positional rather than structured.
