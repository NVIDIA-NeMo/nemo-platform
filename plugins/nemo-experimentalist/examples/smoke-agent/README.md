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
> Why a baseline must not change, and the per-group detail, live in
> `plugins/nemo-experimentalist/docs/`.

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
scripts/sync_verifier.py       refresh the template verifier and records
scripts/build_all_group.py     assemble the combined group the full scenario runs
scripts/record_traces.py       evaluate a group and ingest its traces
```

## Running it

Run the loop **inside a Docker sandbox**. Clone mode gives it a private writable
clone rather than write access to the host checkout, which keeps a run from
touching this directory.

```bash
repo="$(git rev-parse --show-toplevel)"

sbx create --clone --profile external-only --name nemo-experimentalist shell "$repo"
```

`--clone` mounts your checkout read-only and gives the sandbox a private clone to
work in, so a run cannot modify your working tree. NVIDIA employees must also
pass `--profile external-only`.

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
  --env NEMO_DEFAULT_MODEL=default/openai-openai-gpt-5-6-terra \
  --env NEMO_FAST_MODEL=default/openai-openai-gpt-5-6-luna \
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
is what normally configures them. `NEMO_DEFAULT_MODEL` and `NEMO_FAST_MODEL`
override the context, which is what the command above does; the value is an
entity id of the form `<workspace>/<name>`, not a litellm routing string. List
what your platform has with `nemo models list --all-pages`; this local setup uses
`default/openai-openai-gpt-5-6-terra` and
`default/openai-openai-gpt-5-6-luna`. With neither variable set, the run stops at
preflight with "No default model is configured".

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

This matches the repository as it stands rather than carving out a new exception:
the `copyright-fix` hook is scoped to `\.(py|ts)$`, and comparable fixtures
elsewhere — `sdk/python/nemo-platform/tests/sample_file.txt`, the model-spec
`test_data/**/README.md` files, the `automodel` upload fixtures — carry no header
either. Every file here that *is* source does carry one.

## Groups

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

What any individual group measures, and why its baseline must not change, is
documented outside this directory — see the note at the top of this file.

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
healthy. Do not "fix" the agent to make it pass; read the documents referenced at
the top first.

## Timings

Measured on 2026-08-05, one round, two candidates, three tasks per split:

| | |
| --- | --- |
| One split evaluated in containers | ~15 s |
| A full round end to end | ~18 min |

Container evaluation is negligible by design. The cost is the Experimentalist's
own components — the architecture doc, Analyzer, Proposer, and one Coder pass per
candidate — which is the part under test and cannot be optimized away here.
