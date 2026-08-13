<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# smoke-agent

A fast fixture for exercising the Experimentalist loop end to end. It exists to
make a full round cheap enough to run while refactoring, and to let a run be
checked for more than "it completed".

> **Nothing inside `agent/` may describe what this fixture measures.** That
> directory is what `agent_source` points at, so it is copied into every
> candidate workspace and read by the Coder; a description there would hand it
> the diagnosis the fixture exists to test. Everything else here — this file,
> `configs/`, `scripts/`, `dataset/` — is never copied and can say whatever is
> useful. `AGENT-SPEC.md` reaches the LLM components by a separate route and is
> held to the same rule as `agent/`.
>
> The [deliberate weaknesses](#deliberate-weaknesses) section explains why the
> baseline must not change and how each scenario is constructed.

## Prerequisites

- A local NeMo Platform with default and fast Model Entities selected by `nemo setup`
- Docker Engine and Docker Sandboxes (`sbx`)
- `uv`

## Design

- **The agent makes no model calls.** Handlers are regular expressions plus a
  dict lookup over `dataset/_shared/records.json`, so the same instruction always
  produces the same answer and the only stochastic component in a run is the
  Experimentalist itself. The `CompletionClient` in `agent.py` points at an
  unroutable address: an accidental model call fails loudly rather than quietly
  making the agent nondeterministic.
- **Task definitions are local and checked in.** No registry, no NeMo Platform
  for Mode 2, no network inside the task container.
- **One prebuilt image serves every task**, referenced by
  `[environment].docker_image` rather than a per-task Dockerfile. Its tag is a
  content hash of the Dockerfile and the records file, so forgetting to rebuild
  fails a test instead of silently running against stale data.

## Layout

```text
agent/                         ONLY this is copied to the Coder (agent_source)
agent/agent.py                 the code under optimization
agent/main.py                  container entry point
agent/harbor_wrapper.py        Harbor upload + exec adapter
AGENT-SPEC.md                  behaviour contract read by the LLM components
optimizer.yaml                 profile: agent source, spec, g1 datasets
optimizer-full.yaml            profile: the generated combined datasets
optimizer-generalization.yaml  profile: same agent, g4 datasets (see Scenarios)
configs/short.yaml            loop settings shared by the per-group gate checks
configs/full.yaml              loop settings for the multi-round scenario
dataset/_shared/               canonical Dockerfile, records, verifier
dataset/tasks.json             authored task values used to render every curated task
dataset/task-template/         one Harbor task shape, also used by insight mode
dataset/groups/                GENERATED Harbor task sets, gitignored
dataset/insights/              insight mode only, frozen analyst output
scripts/render_tasks.py        render every curated task from the template
scripts/build_image.py         build the image and render/stamp every task
scripts/build_all_group.py     assemble the combined group the full scenario runs
scripts/record_traces.py       evaluate a group and ingest its traces
```

## Running it

Run the loop **inside a Docker sandbox**. Clone mode gives it a private writable
clone rather than write access to the host checkout, which keeps a run from
touching this directory.

```bash
repo="$(git rev-parse --show-toplevel)"

sbx create --clone --name nemo-experimentalist shell "$repo"
```

`--clone` mounts your checkout read-only and gives the sandbox a private clone to
work in, so a run cannot modify your working tree.

> **In a git worktree?** `--clone` refuses to run there, so bind-mount instead:
>
> ```bash
> sbx create --profile developer --name nemo-experimentalist shell "$(pwd)"
> ```
>
> That gives the sandbox write access to this checkout, so the source-mutation
> protection clone mode provides is gone. Check `git status` on the example after
> a run.

```bash
# The image lives in the sandbox's own Docker daemon, so build it there.
sbx exec --workdir "$repo" nemo-experimentalist bash -lc \
  'cd plugins/nemo-experimentalist/examples/smoke-agent && uv run --no-project scripts/build_image.py'
```

`build_image.py` first renders `dataset/groups/` from `dataset/tasks.json` and
`dataset/task-template/`. Do not edit those generated directories; change the
manifest or template and rerun the command instead.

Then run a scenario. `--with ./plugins/nemo-agents` is required: the `agents`
command group lives in a separate workspace package, and without it the CLI fails
with `No module named 'nemo_agents_plugin'`.

```bash
sbx exec --workdir "$repo" \
  --env UV_PROJECT_ENVIRONMENT=/home/agent/.venvs/nemo-platform \
  nemo-experimentalist \
  bash -lc 'uv run --frozen --python 3.13 \
    --package nemo-experimentalist-plugin --with ./plugins/nemo-agents \
    nemo agents experimentalist run \
      --profile plugins/nemo-experimentalist/examples/smoke-agent/optimizer.yaml \
      --no-insight \
      --base-url http://host.docker.internal:8080 \
      --config plugins/nemo-experimentalist/examples/smoke-agent/configs/short.yaml \
      --experiment-dir /tmp/smoke-repair'
```

**Models come from the platform, not from this example.** The Experimentalist
reads a *Model Entity* pair from the active CLI context — `default_model` and
`fast_model`, the second falling back to the first when unset — so `nemo setup`
is what configures them. The value is an entity id of the form
`<workspace>/<name>`, not a Litellm routing string. List what your Platform has
with `nemo models list --all-pages`.

Preflight only checks that a value is *set*, not that the entity exists — a typo
passes `doctor` and fails at the first LLM call, minutes into a run.

**`--base-url` points at a platform, and the sandbox is not the host.** A
container's `localhost` is itself, so a platform running on your machine is
reached at `host.docker.internal:8080`. Without a reachable platform the run
still works — the model pair is what it needs — but every projection of runs and
candidates onto native `ExperimentGroup`/`Experiment` entities fails and logs
`[MIRROR] projection failed`. That is best-effort and never fails a run, so a log
full of it means the platform was unreachable, not that anything went wrong.

Copy the experiment directory back out with `sbx cp` to check the result.

### Run the loop tests

The loop tests are developer-invoked and execute model-written shell inside the
named sandbox. Create the `nemo-experimentalist` sandbox with the command above
before running them. Then run the Mode 1 and Mode 2 suites directly with pytest:

```bash
SANDBOX_VM_ID=nemo-experimentalist uv run --frozen pytest \
  plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_mode_1_loop_e2e.py \
  plugins/nemo-experimentalist/tests/experimentalist/test_smoke_agent_mode_2_loop_e2e.py \
  -m e2e -n 4 --dist loadgroup
```

Pytest writes logs and downloaded experiment artifacts under its temporary test
directory. It does not retry failed runs.

## Scenarios

**The profile picks the scenario, not the config.** What separates a repair run
from a generalization one is the split it runs against, so each has its own
profile:

| Profile | Config | Rounds | A healthy run ends with |
| --- | --- | --- | --- |
| `optimizer.yaml` | `short.yaml` | 2 | the winner beating the baseline |
| `optimizer-generalization.yaml` | `short.yaml` | 2 | the baseline correctly retained |
| `optimizer-full.yaml` | `full.yaml` | up to 5 | every task in the combined group passing |

The first two are opposite tests, so a run is only meaningful once you know which
one you started — and the config cannot tell you, because both use the same one.
That is not an oversight: the scenario config carries loop settings only, and the
schema has no dataset field at all. Which split a run uses lives on the profile,
so the profile is what decides the question.

```bash
# generalization: same agent, held-out split, baseline expected to win
--profile optimizer-generalization.yaml --config configs/short.yaml
```

`full.yaml` is the only one that exercises the evolutionary machinery — survivors
carried between rounds, ranking over more than two candidates, and the
convergence check. It runs against `dataset/groups/_all`, which is **generated
and gitignored**; build it first, or the run loads zero tasks and reports
`No tasks matched the filter(s)` rather than erroring:

```bash
sbx exec --workdir "$repo" nemo-experimentalist bash -lc \
  'cd plugins/nemo-experimentalist/examples/smoke-agent && uv run --no-project scripts/build_all_group.py'
```

Rerun that after changing any group. Not every group is in the combined set —
`build_all_group.py` says which are held out and why.

## Why rendered task files carry no licence header

`instruction.md` and `tests/expected.txt` under `dataset/groups/` are rendered
literal payloads, not source. `expected.txt` is compared byte-for-byte, so a
header would become part of the expected answer and every task would fail;
`instruction.md` is the prompt handed to the agent, so a header would become part
of the question.

The repository's `.copyrightignore` explicitly exempts these task payloads from
SPDX headers. Every source file in this fixture retains the standard header.

## Deliberate weaknesses

smoke-agent is **wrong on purpose**. Five known weaknesses, each paired with a
Harbor task group, let an Experimentalist run prove that it repaired something
rather than merely completed.

**Do not fix them in the baseline agent.** A well-meaning cleanup destroys what
the fixture measures: the baseline passes, the Analyzer gets no failing trace,
and a run that does nothing looks healthy.

Tasks are authored in `dataset/tasks.json` and rendered into `dataset/groups/`
by `scripts/render_tasks.py`, which `scripts/build_image.py` runs. The rendered
tree is gitignored, so edit the manifest rather than its output. Every group has
train and validation splits; every group except `g4-dispatch-order` also has five
`insight-evidence` tasks for the Analyst and Mode 1 loop.

### G1 — no aggregation capability

Nothing sums or averages a numeric field. `solve` dispatches only to
`handle_lookup`, `handle_list`, and `handle_count`, so a total-hours question
falls through to `FALLBACK`. This is the only missing capability; G2–G5 are
flawed existing paths, so G1 exercises the Proposer more than the Coder.

`g1-aggregation` includes department and role sums in both splits. Train covers
research (`total=29`) and engineer (`total=20`); validation covers analyst
(`total=9`) and ops (`total=13`). A repair must read the requested scope rather
than hardcode it. A correct repair adds a scoped aggregation handler to dispatch.

### G2 — name pattern too narrow

`LOOKUP_RE` uses `([A-Za-z ]+)`, so apostrophes, hyphens, and non-ASCII names
fall through to `FALLBACK`. `g2-name-patterns` covers O'Brien, Zoë Washington,
and Ann-Marie Cruz while retaining plain-ASCII controls. A correct repair widens
the pattern; `str.isalpha()` is not equivalent because it accepts Unicode names
that the original ASCII regular expression rejects.

### G3 — instruction clipped before dispatch

`solve` truncates instructions to `MAX_INSTRUCTION_CHARS = 240`, so a long
preamble can remove the question before any handler sees it. `g3-long-inputs`
uses a roughly 320-character preamble and a roughly 650-character variant, so a
small limit increase is insufficient. The `trailing-prose` control puts the
question first and catches a bad repair that reads only a clipped tail. A correct
repair raises or removes the limit.

### G4 — dispatch order shadows the count handler

`LIST_RE` accepts `how many` and runs before `COUNT_RE`, so counting questions
produce a list of names. This is the only wrong-shaped answer rather than a
fallback, producing `reward 0` with `shape_ok 1.0`. `g4-dispatch-order` trains
on department counts and validates role-scoped counts: reordering alone is not
enough because the count pattern must widen too. Its healthy outcome retains the
baseline after the train-only fix fails validation.

### G5 — missing and empty data not handled

`handle_lookup` raises for an absent name, while an empty stored value produces
an empty answer instead of `unknown`. The top-level catch returns `FALLBACK` so
Harbor records a scored failure rather than a harness error. `g5-edge-cases`
covers absent names and Karl Jung's empty `role`; correct repairs explicitly
handle absent records and empty fields.

### Keep the groups orthogonal

Each group must evidence only its own weakness. The shared records file is a
coupling surface: Ada Lovelace and Grace Hopper are non-empty controls; Zoë,
O'Brien, and Ann-Marie serve G2; Karl Jung has an empty `role` but integer hours.
His hours stay `0`, not empty, because an empty value in the `ops` department
would force G1 aggregation to handle G5 robustness. Check this separation when
adding a task or record.

The baseline guards pin agent behavior and the records table, but they do not
pin individual split assignment. Check `dataset/tasks.json` after changing the
manifest.

## Scenario matrix

Every group is a self-contained train/validation pair of six tasks — per split,
two that fail at baseline and one that already passes. That control is the point:
it makes a destructive fix cost reward instead of passing unnoticed, and it means
a group's score can fall as well as rise.

| Group | What a run against it tests | Backs | In `_all` |
| --- | --- | --- | --- |
| `g1-aggregation` | **Repair.** Train shows two kinds of filter, so a general fix is reachable — and a hardcoded one fails validation. | `short.yaml` | yes |
| `g2-name-patterns` | Widening a pattern that is too narrow. Train shows two kinds of awkward name, validation a third. | `full.yaml` | yes |
| `g3-long-inputs` | A constant rather than logic — the one `edit_config` in the set, so a run exercises a different path through the Coder. | `full.yaml` | yes |
| `g4-dispatch-order` | **Generalization.** The tempting fix passes train and fails validation, so a healthy run *keeps the baseline*. | `short.yaml` | no |
| `g5-edge-cases` | Several changes that score only when all are made, whose partial states are indistinguishable in the output. The hardest here. | `short.yaml` | no |

Two groups are held out of the combined set, for different reasons.

`g4-dispatch-order`'s healthy outcome — baseline retained — is the opposite of
the combined scenario's, and one run cannot assert both.

`g5-edge-cases` is only reachable with trajectory scoring on, and the combined
scenario runs with it off: measured over runs made after the spec stated the
sentinel, no candidate closed it without a goal tree and most did with one.
Trajectory scoring is not dependable enough to leave on yet, so the group is out
until it is. `build_all_group.py` records the numbers and the condition for
putting it back. Run it on its own with `short.yaml` in the meantime — it is a
repair-shaped split.

The groups are not interchangeable and not redundant. Each was built so that a
run against it answers a different question about the loop, which is why the
combined scenario wants several at once rather than more tasks from one:

- Several independently addressable groups let a single round produce genuinely
  *different* candidates, and let a later round inherit one fix and add another.
  A one-group dataset can show neither.
- They differ in the kind of edit they call for, so a run exercises more than one
  path through the Coder.
- The groups differ in difficulty. The easier ones give an early round something
  to find, so a run that stalls later still shows the machinery working; the
  harder ones keep the ceiling out of reach of a shallow fix.

The deliberate-weaknesses section above explains the baseline and split
constraints behind each scenario.

## Checking a run

The Mode 1 and Mode 2 E2E tests check the experiment artifacts themselves. They
verify source changed, held-out tasks pass, controls do not regress, and the
Analyzer named each group's problem. They also verify that G4 keeps the baseline
when a train-only change fails to generalize.

**Also run the guard suite after every loop run:**

```bash
uv run pytest plugins/nemo-experimentalist/tests/experimentalist/ -k smoke -q
```

It pins this fixture's baseline behaviour. A failure there means the fixture
itself changed, which makes every later run meaningless while still looking
healthy. Do not "fix" the agent to make it pass; read the deliberate-weaknesses
section first.

## Timings

Measured on 2026-08-05, one round, two candidates, three tasks per split:

| | |
| --- | --- |
| One split evaluated in containers | ~15 s |
| A full round end to end | ~18 min |

Container evaluation is negligible by design. The cost is the Experimentalist's
own components — the architecture doc, Analyzer, Proposer, and one Coder pass per
candidate — which is the part under test and cannot be optimized away here.

## Next steps

- Read [Deliberate weaknesses](#deliberate-weaknesses) before changing the baseline.
- Run the [asset guards](../../tests/experimentalist/test_smoke_agent_assets.py) after changing the image, task template, or manifest.
- Use `optimizer-full.yaml` with `configs/full.yaml` to exercise the combined scenario.
