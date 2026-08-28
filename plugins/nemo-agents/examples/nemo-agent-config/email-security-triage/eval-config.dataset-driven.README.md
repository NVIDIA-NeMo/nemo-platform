<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Dataset-driven evaluation — Email Security Triage

`eval-config.dataset-driven.yml` and `dataset.jsonl`, beside this note, score the
[email-security-triage](README.md) agent. Studio's Run Evaluation flow seeds them into a
fileset; the CLI reads them from here (see README Step 5). Either way they are yours to
edit — nothing regenerates them.

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
`phishing` or `benign` on the first line and its reasoning after. Note the row arrives as plain
text, not as the `{user_message, emails[]}` JSON the task-driven suite sends — routing it to
triage rather than to the general review is part of what this suite exercises.

## The metric

| Metric         | Output         | Range | Checks                                      |
| -------------- | -------------- | ----- | ------------------------------------------- |
| `llm-judge`    | accuracy       | 0–1   | First line of the response matches `label`  |
| `string-check` | `string-check` | 0/1   | First line is a bare `phishing` or `benign` |

The `string-check` is a **routing** assertion, not an accuracy one: every row asks the same
legitimacy question, so every row must reach the triage contract. It scores 1 whenever line 1 is
one of the two verdict words, regardless of which. Read it alongside `accuracy` — accuracy near
zero while routing holds is a judgement problem; both near zero is a routing problem. Routing is
asserted from the output contract rather than from tool calls, which a Fabric agent's responses do
not carry (see the task-driven README).

The judge reads the **first line**, not the last. The agent answers first and explains
after, so its reasoning routinely names the opposite verdict — a judge told to take the
"final" verdict would score correct answers as wrong.

## Reading the results

Expect a mid-range score, not a perfect one; the dataset was built to leave headroom.

Look at the shape of the misses, not just the headline number. The agent is a security
assistant told to hunt social-engineering signals, so it tends to lean cautious — check
whether your errors skew toward benign mail called phishing, and read that tendency
against the rows the dataset deliberately made contestable.

Read the routing check alongside accuracy. While routing holds, the misses are judgement
calls; if both fall together, the agent answered as the wrong capability.

A near-zero score means something mechanical, not a collapsed agent: most likely the judge
reading the wrong line, or the agent answering as a different capability. The `string-check`
tells the two apart — it stays at 1.0 in the first case and collapses with accuracy in the
second.

## Editing this config

`dataset` carries a placeholder, `<workspace>/<fileset>#dataset.jsonl`, because no such
fileset exists in a fresh workspace. Studio's Run Evaluation flow rewrites it at seed time
so the config and its data travel together. A CLI run must set a real reference first —
upload `dataset.jsonl` and point at it (README Step 5).

If you point it elsewhere, keep the four field names — the `prompt_template` and the judge
both reference them.

Metric templates get string operations only; there is no JSON parsing, which is why the
answer is positional rather than structured.

This config is authored in YAML and its task-driven sibling in JSON, to show that both
are accepted: Studio's upload and the CLI's `--spec-file` sniff the content, not the
extension. Converting between them is lossless — ship one format per file rather than
the same config twice.
