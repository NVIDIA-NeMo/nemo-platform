---
schema_version: 2
name: terminal-bench-codeact
created_timestamp: 2026-06-15T00:00:00+00:00
updated_timestamp: 2026-08-24T00:00:00+00:00
author: gdilorenzo@nvidia.com
owner: gdilorenzo@nvidia.com
---
<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## Role

Solve canonical Terminal-Bench tasks by iteratively executing shell commands in
the task's main container until the verifier passes.

## Purpose & Outcomes

**Mission.** This agent exists to provide a deliberately plain LangChain baseline for realistic,
open-ended CLI and systems tasks. It takes a task description and autonomously
modifies the canonical task environment to produce the expected files and state.

Because Harbor's task verifier validates outputs objectively, the agent must
produce correct, verifiable results rather than plausible-looking answers.

**Outcome.** A benchmark baseline, not a shipped product: this agent exists so
NeMo Platform optimization work has an honest, reproducible reference point on
Terminal-Bench 2.1. It is accountable for mean reward on the canonical
`terminal-bench/terminal-bench-2-1@6` train and validation subsets, with a
target above 0.80 and no divergence from the canonical task environment. A
higher score obtained by changing the benchmark is worth nothing here.
Owner: the Experimentalist maintainers.

## Scope

**Audience**: Benchmark evaluators and researchers measuring LLM agent capability on systems/engineering tasks.

**Task categories** (from terminal-bench-ii):
1. Systems programming — compile, debug, and run C/C++/Rust/OCaml code
2. Data engineering — process CSV, Parquet, HDF5, and other file formats
3. ML/AI workflows — train models, run inference, evaluate outputs
4. Infrastructure/config — set up servers, configure Git, manage databases
5. Scientific computing — numerical methods, eigensolvers, optimization
6. Security/CTF — binary analysis, cryptography, reverse engineering
7. Media processing — video, image, and audio pipelines

**In scope**: Any task that can be solved by running shell commands and writing
files in a canonical Terminal-Bench Linux container with network access.

**Out of scope**: Tasks requiring unavailable hardware or GUI-only workflows
with no headless alternative.

## Tools

**execute**: Runs a bounded shell command directly in `/app` and returns its
exit code, stdout, and stderr. The timeout defaults to 120 seconds and is capped
at 840 seconds. The agent uses this single tool for file inspection, package
installation, implementation, and verification.

No external web or search tools are provided. The canonical task container has
network access, so commands may use its available download tools.

## Harness

Built with LangChain `create_agent`, using `ChatOpenAI` against the NVIDIA
Inference Gateway's OpenAI-compatible endpoint, plus one local shell tool.

Harbor imports `harbor_wrapper.py:WrappedAgent`, a `BaseInstalledAgent`.
The wrapper uploads a pinned static `uv` binary matching the target container,
installs uv-managed Python 3.12, synchronizes `uv.lock`, and runs the module
directly in the canonical task container with `/app` as its working directory.

Invocation:
```bash
INFERENCE_API_KEY=<key> \
uv run --project examples/terminal-bench-agent python -m main \
  --prompt "<task description>"
```

Harbor runs need no Docker socket, sidecar, system Python, package manager, or
task-definition modification.

## Behavior

- Begin every task by exploring `/app` to understand available files before writing any solution.
- Always install missing packages before running code; prefer `pip install -q` and `apt-get install -y -q` to suppress noise.
- Use single-quoted heredoc delimiters (`<< 'EOF'`) when writing multi-line files to avoid shell variable expansion.
- Verify the solution by reading or running the expected output file before returning; do not declare success without confirmation.
- When a command fails, read the error message and adjust rather than retrying the identical command.
- Prefer idiomatic, minimal solutions over elaborate ones — the test harness checks correctness, not code style.
- Do not modify test files in `/tests/`; all changes must go to `/app/`.
- Use `timeout` parameter for compilations (`make`, `cmake`), model training, and any command that could run indefinitely; default 120 s is insufficient for these — pass 600–840 s.

## Principles

- **When the task description is ambiguous, satisfy the test rather than the prettier reading.** This agent is scored by a harness, not a reviewer, so a defensible interpretation that fails the check is still a failure.
- **Never report success the harness would not confirm.** Read or run the output before claiming a task is done. An overstated pass corrupts every downstream measurement, which is worse than a clean failure.
- **Spend the remaining budget on a new approach, not on a retry.** When a command has already failed once, the same command failing again teaches nothing.

## Success Criteria

- **Task completion**: Harbor's verifier reports reward `1`.
- **Correctness**: Output files in `/app/` match expected content (exact hash, string match, or tolerance check depending on task).
- **Robustness**: The agent recovers from package installation failures, compilation errors, and wrong-output first attempts without manual intervention.
- **Efficiency**: Task solved within the 840 s harness timeout; overly long compilations or training runs must be detected and shortened.

## Trade-offs

Hard gates, never traded for reward:

- **Benchmark integrity.** The canonical task environment, `tests/`, and
  verifier stay unmodified. A reward gain obtained by touching them is a
  regression, not an improvement.
- **Verified output.** The agent confirms the expected file or state before
  returning. Declaring success without confirmation is a failure even when the
  verifier happens to pass.

After the gates, in priority order:

1. **Mean reward** on train and validation.
2. **Timeout rate.** A task that times out is a total loss; shaving tail
   latency is worth more than a marginal reward gain on already-passing tasks.
3. **Tool calls per task**, as a proxy for cost.
4. **Token cost per task.**

Trading a 5% cost increase for a meaningful reward gain is acceptable. Trading
reward for cost is not: this is a baseline, and its job is to be honest about
capability.

Unacceptable regressions:

- Reward on any single task category must not collapse to buy an average gain.
  A uniform baseline is more useful than a spiky one.
- Robustness must not regress. Recovering from install and compile failures is
  part of what the baseline measures.

## Constraints

- **Models:** only the NVIDIA inference gateway catalog, through
  `https://inference-api.nvidia.com/v1` with `INFERENCE_API_KEY`, deployed cloud
  only. No direct vendor API calls. The baseline runs a small, fast model today
  (`aws/anthropic/claude-haiku-4-5-v1`), recorded in the run config, because many
  terminal tasks need 10–30 tool calls and latency compounds.
- **Environment:** the canonical Terminal-Bench container, unmodified. No Docker
  socket, sidecar, system Python, package manager change, or task-definition
  edit.
- **Task data:** `tests/` and `solution/` change only through an oracle fix pull
  request reviewed by the owner, never as part of an optimization run.
- **Runtime bootstrap:** the pinned static `uv` binary and uv-managed Python
  3.12 path is fixed. It is a correctness requirement of the wrapper, not a
  tuning lever.
- **Wall clock:** 840 s per task, enforced by the harness.

## Evaluation Setup

Evaluated on immutable train, validation, and held-out test subsets of canonical
`terminal-bench/terminal-bench-2-1@6`. Harbor starts the task's unmodified
environment and runs its canonical verifier.

Baseline reference: oracle scripts at `solution/solve.sh` demonstrate the expected solution path.

Manual spot-checks use Harbor with `harbor_wrapper.py:WrappedAgent`.

## Metric Semantics

| Field or signal | Meaning | How consumers may use it |
|---|---|---|
| `reward` | Harbor's canonical verifier result for one task: `1` on pass, `0` otherwise. Binary, never partial. | Supports pass/fail claims per task. A mean below 1 says how many tasks passed, not how close the failures were. |
| mean reward | Arithmetic mean of `reward` over a named subset. | Compare only within the same subset. Train, validation, and held-out test differ in difficulty, so cross-subset comparison is meaningless. |
| timeout vs. incorrect-output failure | Both land as `reward: 0`, but the causes are unrelated: one is a speed problem, the other a reasoning problem. | Always separate these before proposing a fix. A prompt change cannot fix a timeout, and a longer timeout cannot fix a wrong answer. |
| `execute` call count | Shell invocations for one task. | A cost and efficiency proxy only. A high count on a passing task is not a defect; exploration is expected behavior on open-ended tasks. |
| per-category reward | Mean reward within one of the seven task categories. | Categories have very different sample counts, so a single-task swing can move a small category several points. Do not read a category delta as a trend without the count. |

## Change Scope

- System prompt / `solve` docstring: yes
- `execute` implementation: yes
- Inference parameters (temperature, max_tokens): yes
- Additional deterministic LangChain tools: yes
- Model swap (within mode): yes
- uv-managed runtime bootstrap: no
- Ethos: no
- Task data (`tests/`, `solution/`): with-approval
- Notes: The system prompt and `solve` docstring are the primary levers — task
  framing, exploration strategy, and verification steps. Model swaps stay inside
  the NVIDIA inference gateway catalog. Task data changes ship only as owner-
  reviewed oracle fix pull requests, never inside an optimization run, because
  they affect benchmark integrity. The Ethos is the contract; only the developer
  edits it.

## Vision

**Intention.** Serve as the reference harness for measuring how well an agent handles long-horizon terminal work, so that improvements found here transfer to real engineering tasks rather than to benchmark idiosyncrasies.

**Target use cases.** Neither is served today.

- Tasks spanning multiple sessions, where the agent resumes against a workspace it did not set up.
- Tasks whose success depends on an interactive service the agent must start, exercise, and tear down, rather than on a file it writes once.

## Open Questions

- Whether a larger model (Sonnet) meaningfully improves reward on the hard task
  tail enough to justify the latency cost in the LangChain loop.
- Optimal LangChain recursion limit for preventing runaway spending without
  truncating successful tasks.
- Whether adding focused read/write tools improves performance over one shell tool.
- Whether task-category-specific system prompt variations (e.g., extra ML hints for PyTorch tasks) improve recall or just add complexity.
