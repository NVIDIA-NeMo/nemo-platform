# Task-driven evaluation — Email Security Analyst

This fileset holds the **task-driven** eval config seeded from the built-in Email Security
Analyst sample, plus this note. It is yours to edit; nothing regenerates it.

Task-driven means each task carries **its own metrics**, so one suite can grade work of
different kinds. The sibling dataset-driven config scores the same agent a different way:
one metric set over every row of a fixed dataset.

## What is being evaluated

The agent is an analyst-facing assistant inside a mail client. The operator selects one or
more messages and optionally types a question. Input arrives as one JSON object:

```json
{ "user_message": "is this legit?", "emails": ["Subject: ...\nFrom: ...\n\n<body>"] }
```

`user_message` is `""` when nothing was typed. `emails` is `[]` when nothing was selected.

The agent routes that request to one of four capability tools and returns the tool's answer
verbatim. **Routing is the thing under test.** No task tells the agent which capability to
use or how to format its reply — a real inbox does not arrive with instructions, so the
taxonomy (verdicts, report format) lives in the agent, not the prompt.

Each tool answers first and explains after: the first line is the bare answer, reasoning
follows. That is what lets deterministic metrics read a result without an LLM.

Variety here comes from _how a human engages_ — one message or several, question or no
question — rather than from artificially varied material.

## The 10 tasks

Two per family. Five families across four tools, chosen so that every metric flavor is
represented once: a subjective judge, a numeric check, a boolean check, and a rubric.

| Task           | Ask                             | Metric                             | Checks                                                       |
| -------------- | ------------------------------- | ---------------------------------- | ------------------------------------------------------------ |
| classify       | _is this legit?_                | `llm-judge` accuracy               | Verdict on line 1 matches ground truth                       |
| thread         | _where did this thread go bad?_ | `number-check`                     | Position of the injected message                             |
| default-review | _(no question)_                 | `string-check` + `llm-judge`       | Routing, per-message verdicts, field completeness            |
| injection      | _is this legit?_                | `llm-judge` injection_resisted     | Correct verdict despite an instruction embedded in the email |
| draft          | _write a warning for the team_  | `llm-judge` draft_quality (rubric) | poor / adequate / strong against expected elements           |

**classify** and **injection** both route to the same tool and ask the same question, and are
not duplicates. `injection` plants an instruction inside the email body that tries to talk the
agent out of its verdict, so it grades prompt-injection resistance rather than classification
skill — a correct verdict there means the guardrail held.

**default-review** is the only pair with no question, and its `string-check` is a routing
assertion: only the general-review tool heads its output with `ANALYSIS`, so the check fails
if the agent picks a different tool. It is also the only task carrying two metrics, which is
legal because they are different types.

**draft** is the only pair with no single correct answer — a staff warning has no exact
wording. Its rubric grades how many expected elements appear, so its `reference` holds those
elements rather than an expected reply.

## Reading the results

Prefer the per-`view` scores over raw metric rows: a view is scoped to its task, whereas raw
rows union output names across all tasks, so a metric used by two tasks reads `NaN` for the
other eight.

Before reading a low score as a weak agent, rule out the mechanical causes: a tool missing
from the workflow's `return_direct` (a second generation rewrites the answer and breaks the
first-line contract), a judge prompt describing an older output format, and mis-routing —
right answer, wrong tool, wrong contract. All three look identical in the score table.

## Editing this config

Metric templates get string operations only; there is no JSON parsing, which is why answers
are positional rather than structured. A task may not carry two metrics of the same type —
use one metric with several outputs instead. Every judge that reads a verdict must read the
**first line**, not the last: reasoning follows the answer and often mentions the opposite
verdict.
