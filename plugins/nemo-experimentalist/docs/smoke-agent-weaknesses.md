<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# smoke-agent: the deliberate weaknesses

`examples/smoke-agent` ships an agent that is **wrong on purpose**. Five known
weaknesses, each paired with a group of Harbor tasks that surfaces it, so an
Experimentalist run can be asserted to have *repaired* something rather than
merely completed.

**Do not fix them in the agent.** A well-meaning cleanup silently destroys what
the fixture measures: with the weakness gone, the baseline passes, the Analyzer
gets no failing trace, and a run that does nothing looks identical to a run that
works.

## Why this file is here and not next to the agent

`get_agent_code` copies the example directory into `source-agent/` minus
`_AGENT_COPY_EXCLUDE_NAMES` (`__pycache__`, `.git`, `.claude`, `.uv`, `.venv`,
`artifacts`, `dataset`, `eval-and-optimize`, `scratch`). **Everything else under
the example root is readable by the Coder**, including `AGENT-SPEC.md`, which
`coder.py` reads before any source file.

So a description of the weaknesses inside the example would hand the Coder the
diagnosis the fixture exists to test, and a run could pass with a broken
Analyzer. That is why `agent.py` carries only ordinary engineering comments,
`AGENT-SPEC.md` has no known-gaps section, and the frozen Insights live under
`dataset/` — the one in-example directory the copy excludes.

There is evidence this matters and works: the analyst diagnosed G1 correctly from
traces alone, with no hint available in the source or the spec.

## The five weaknesses

All line references are to `examples/smoke-agent/agent/agent.py`.

### G1 — no aggregation capability

**What.** Nothing sums or averages a numeric field. `solve` dispatches over
`handle_lookup`, `handle_list`, `handle_count`; none matches "what is the total
`<field>` for …", so every aggregation question falls through to `FALLBACK`.

**Odd one out.** This is the only *missing* capability; G2–G5 are flawed code
paths that exist. There is no wrong code to find, only absent code, so G1's tasks
exercise the Proposer more than the Coder.

**Tasks.** `dataset/groups/g1-aggregation/` — train sums by department
(`total=29`, `total=13`); validation sums with no scope (`total=42`) and by
*role* (`total=20`). A fix that hardcodes a department filter passes train and
fails validation. That is the generalization axis.

**A correct repair** adds a handler that sums a field over a record subset, with
the scope taken from the question rather than assumed, and inserts it into the
dispatch tuple.

### G2 — name pattern too narrow

**What.** `LOOKUP_RE`'s name group is `([A-Za-z ]+)`, so any name carrying an
apostrophe, a hyphen, or a non-ASCII character fails to match at all and falls
through to `FALLBACK`.

**Tasks.** `dataset/groups/g2-name-patterns/` — `O'Brien`, `Zoë Washington`,
`Ann-Marie Cruz`. Controls are plain-ASCII lookups that already work.

**A correct repair** widens the character class. Note `str.isalpha()` is *not* a
valid test for "would this name match" — it is Unicode-aware and accepts `Zoë`
while the agent's ASCII class rejects it. The guard test uses the agent's own
class for exactly this reason.

### G3 — instruction clipped before dispatch

**What.** `solve` truncates to `MAX_INSTRUCTION_CHARS = 240` before dispatching,
so a question preceded by a long preamble is cut off and matches nothing.

**Tasks.** `dataset/groups/g3-long-inputs/` — a ~300-character reporting-policy
preamble in front of a question that works without it.

**The control is load-bearing.** `trailing-prose` puts the question *first* and
the prose after, so it passes at baseline **and** would break under a fix that
reads only the tail of a clipped instruction. It catches a specific bad repair.

**A correct repair** raises or removes the limit.

### G4 — dispatch order shadows the count handler

**What.** `LIST_RE` is `(?:list|how many) .*? in the (\w+) department` — the
`how many` alternative belongs to `COUNT_RE` — and `solve` consults
`handle_list` first. Counting questions are therefore answered with a list of
names.

**Odd one out.** This is the only group whose failure is a *wrong-shaped answer*
rather than the fallback, so it scores `reward 0` with `shape_ok 1.0`. G1, G2,
G3 and G5's missing-record mode all fall back to prose and score `shape_ok 0`.
Measured: G4 train aggregates to `reward 0.333, shape_ok 1.0`, G5 validation to
`0.333, 0.333`. The two groups are separable from aggregates alone.

**Two halves, one repair.** `LIST_RE` and the dispatch tuple order are a matched
pair. Changing either alone leaves the shadowing in place.

**Tasks.** `dataset/groups/g4-dispatch-order/` — train counts people per
department; validation counts *by role within* a department, which matches
`LIST_RE` but **not** `COUNT_RE`. So reordering the tuple alone still fails
validation; the count pattern has to widen too.

### G5 — missing and empty data not handled

**What.** Two distinct failure modes:

- `handle_lookup` resolves a record with `next(r for r in … if r["name"] == name)`,
  which **raises** when the name is absent. `solve`'s top-level `except` catches
  it and returns `FALLBACK`.
- An empty stored value yields an empty right-hand side (`role=`) rather than a
  documented `role=unknown`.

**Why the catch exists.** Without it the process exits non-zero, the wrapper
raises, and Harbor records a *harness error* rather than a scored 0 — which
leaves the Analyzer nothing to read. Verified: G5 trials complete with
`status=completed` and reward 0. The catch controls the exit code, not the trace;
NOOA already records the exception on the failing handler's span.

**Tasks.** `dataset/groups/g5-edge-cases/` — a name absent from the records, and
Karl Jung's empty `role`. Expected answers use `unknown`.

## Orthogonality, including the data

Each group's tasks must supply evidence for **its own weakness only**, so a run's
failing traces point at one root cause. That extends to `records.json`, which all
five groups share — the data is a coupling surface as much as the code is.

Current assignment, pinned by `test_smoke_agent_baseline.py`:

| Record | Serves | Must stay |
| --- | --- | --- |
| Ada Lovelace, Grace Hopper | controls, G1 engineer sum | plain ASCII, non-empty, int hours |
| Zoë Washington, O'Brien, Ann-Marie Cruz | G2 | non-empty `role`, int `hours` |
| Karl Jung | G5 empty-field mode | empty `role`, **int `hours`** |

Karl Jung's `hours` is `0`, not empty, and that is deliberate: an empty `hours`
sits in `ops`, which G1 aggregates, so it would force a G1 fix to absorb G5's
robustness.

This has already gone wrong once through a *task* rather than the data. G3's
`preamble-long-dept` originally looked up a name absent from the records, so
closing G3 alone would have left it failing on G5's missing-record path. Check
both when adding either.

## If a guard test fails

`test_smoke_agent_baseline.py` and `test_smoke_agent.py` pin every behaviour
above. A failure almost always means the agent was "fixed" rather than that the
tests are wrong. Confirm against this document before changing either.
