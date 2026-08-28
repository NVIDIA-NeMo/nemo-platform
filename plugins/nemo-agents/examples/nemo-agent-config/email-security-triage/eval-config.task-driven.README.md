<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Task-driven evaluation — Email Security Triage

`eval-config.task-driven.json`, beside this note, scores the
[email-security-triage](README.md) agent. Studio's Run Evaluation flow seeds it into a
fileset; the CLI reads it from here (see README Step 5). Either way it is yours to edit —
nothing regenerates it.

Task-driven means each task carries **its own metrics**, so one suite can grade work of
different kinds. The sibling dataset-driven config scores the same agent a different way:
one metric set over every row of a fixed dataset.

## What is being evaluated

The agent is an analyst-facing assistant inside a mail client. The operator selects one or
more messages and optionally types a question. Input arrives as one JSON object:

```json
{
  "user_message": "is this legit?",
  "emails": ["Subject: ...\nFrom: ...\n\n<body>"]
}
```

`user_message` is `""` when nothing was typed. `emails` is `[]` when nothing was selected.

The agent routes that request to one of four capabilities and answers as that capability.
**Routing is the thing under test.** No task tells the agent which capability to
use or how to format its reply — a real inbox does not arrive with instructions, so the
taxonomy (verdicts, report format) lives in the agent, not the prompt.

Each capability answers first and explains after: the first line is the bare answer, reasoning
follows. That is what lets deterministic metrics read a result without an LLM.

Variety here comes from _how a human engages_ — one message or several, question or no
question — rather than from artificially varied material.

## The 10 tasks

Two per family. Five families across four tools, chosen so that every metric flavor is
represented once: a subjective judge, a numeric check, a boolean check, and a rubric.

| Task           | Ask                             | Metric                                              | Checks                                                       |
| -------------- | ------------------------------- | --------------------------------------------------- | ------------------------------------------------------------ |
| classify       | _is this legit?_                | `llm-judge` accuracy + `string-check`               | Verdict on line 1 matches ground truth; routing              |
| thread         | _where did this thread go bad?_ | `number-check`                                      | Position of the injected message (and routing, see below)    |
| default-review | _(no question)_                 | `string-check` + `llm-judge`                        | Routing, per-message verdicts, field completeness            |
| injection      | _is this legit?_                | `llm-judge` injection_resisted + `string-check`     | Correct verdict despite an instruction embedded in the email |
| draft          | _write a warning for the team_  | `llm-judge` draft_quality (rubric) + `string-check` | poor / adequate / strong against expected elements; routing  |

**classify** and **injection** both route to the same capability and ask the same question, and are
not duplicates. `injection` plants an instruction inside the email body that tries to talk the
agent out of its verdict, so it grades prompt-injection resistance rather than classification
skill — a correct verdict there means the guardrail held.

**default-review** is the only pair with no question, and its `string-check` is a routing
assertion: only the general review heads its output with `ANALYSIS`, so the check fails if
the agent answers as a different capability.

**draft** is the only pair with no single correct answer — a staff warning has no exact
wording. Its rubric grades how many expected elements appear, so its `reference` holds those
elements rather than an expected reply.

## Routing is asserted, not inferred

Routing is what this suite exists to measure, so every family asserts it — through **output
shape**, not tool introspection. Each capability opens with a distinct first line, so a
deterministic check proves which one answered:

| Task           | Routes to         | Routing assertion                              |
| -------------- | ----------------- | ---------------------------------------------- |
| classify       | `triage_message`  | line 1 is `phishing` or `benign`               |
| injection      | `triage_message`  | same                                           |
| thread         | `trace_thread`    | implicit — see below                           |
| default-review | `review_messages` | line 1 starts with `ANALYSIS`                  |
| draft          | `draft_warning`   | line 1 is **not** a verdict word or `ANALYSIS` |

`thread` carries no extra metric: its `number-check` already reads a bare integer off line 1,
which no other capability emits, so any misroute scores 0 there anyway. A second `number-check`
would also be illegal — a task may not carry two metrics of the same type.

The `draft` assertion is exclusion-based, so it is the loose one: it proves the answer is not a
verdict or a review, not that it is a warning. A misroute to the thread capability would emit a
bare integer and pass it. Its `llm-judge` rubric is what catches that, so read the two together.

The new checks live in a **`routing` view**, which spans the **6 tasks that carry one**
(classify, injection, draft). `thread` and `default-review` read `NaN` in that view; their
routing signal is inside their own family view. The routing checks are deliberately kept out of
the family views so a misroute does not silently deflate a family's headline score.

Routing is read from output contracts rather than tool calls because a Fabric agent's tool calls
never reach the evaluator: the chat-completions response is built with `content` only
(`fabric/server.py` `_to_chat_completion_response`), and `agent_inference.py` re-synthesizes the
response from the content string regardless. A `tool-calling` metric run here does not error — it
reports 0.0 on every row, silently. Do not add one.

## Reading the results

Prefer the per-`view` scores over raw metric rows: a view is scoped to its task, whereas raw
rows union output names across all tasks, so a metric used by two tasks reads `NaN` for the
other eight.

Before reading a low score as a weak agent, rule out the mechanical causes: a judge prompt
describing an older output format, and mis-routing — right answer, wrong capability, wrong
contract. Both look identical in a family score table, which is what the `routing` view is
for: check it first. A family score that collapses while `routing` holds is a real capability
gap; both collapsing together is a routing problem.

## Editing this config

Metric templates get string operations only; there is no JSON parsing, which is why answers
are positional rather than structured. A task may not carry two metrics of the same type —
use one metric with several outputs instead. Every judge that reads a verdict must read the
**first line**, not the last: reasoning follows the answer and often mentions the opposite
verdict.
