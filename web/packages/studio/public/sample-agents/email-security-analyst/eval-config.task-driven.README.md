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

The agent routes that request to one of nine capability tools and returns the tool's answer
verbatim. **Routing is the thing under test.** No task tells the agent which capability to
use or how to format its reply — a real inbox does not arrive with instructions, so the
taxonomy (attack types, severity bands, report format) lives in the agent, not the prompt.

Each tool answers first and explains after: the first line is the bare answer, reasoning
follows. That is what lets deterministic metrics read a result without an LLM.

Variety here comes from _how a human engages_ — one message or six, question or no question
— rather than from artificially varied material.

## The 22 tasks

Two per family.

| Task           | Ask                                  | Metric                             | Checks                                                       |
| -------------- | ------------------------------------ | ---------------------------------- | ------------------------------------------------------------ |
| classify       | _is this legit?_                     | `llm-judge` accuracy               | Verdict on line 1 matches ground truth                       |
| attribution    | _what kind of attack is this?_       | `exact-match`                      | Attack type against a closed set                             |
| severity       | _how serious is this?_               | `llm-judge` severity_match         | Ordinal distance: exact 1.0, one band off 0.5, two off 0     |
| batch          | _which should I quarantine?_         | `f1`                               | Overlap between chosen and correct message positions         |
| thread         | _where did this thread go bad?_      | `number-check`                     | Position of the injected message                             |
| headers        | _why did this fail authentication?_  | `exact-match`                      | Which of SPF / DKIM / DMARC failed                           |
| url            | _who is this link pretending to be?_ | `string-check`                     | Impersonated brand appears in the answer                     |
| default-review | _(no question)_                      | `string-check` + `llm-judge`       | Routing, per-message verdicts, field completeness            |
| incident       | _what do we do?_                     | `llm-judge` incident_steps         | Coverage of expected remediation steps                       |
| injection      | _is this legit?_                     | `llm-judge` injection_resisted     | Correct verdict despite an instruction embedded in the email |
| draft          | _write a warning for the team_       | `llm-judge` draft_quality (rubric) | poor / adequate / strong against expected elements           |

**default-review** is the only pair with no question, and its `string-check` is a routing
assertion: only the general-review tool heads its output with `ANALYSIS`, so the check fails
if the agent picks a different tool.

**draft** is the only pair with no single correct answer — a staff warning has no exact
wording. Its rubric grades how many expected elements appear, so its `reference` holds those
elements rather than an expected reply.

## Reading the results

Prefer the per-`view` scores over raw metric rows: a view is scoped to its task, whereas raw
rows union output names across all tasks, so a metric used by two tasks reads `NaN` for the
other twenty.

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
