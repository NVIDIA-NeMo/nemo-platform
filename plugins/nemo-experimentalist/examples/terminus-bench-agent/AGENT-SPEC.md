---
name: terminus-bench-agent
created_timestamp: 2026-06-15T00:00:00+00:00
author: gdilorenzo@nvidia.com
---
<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

## Role

Improve Harbor's `terminus-2` code agent through its actual source checkout.
Experimentalist copies the Harbor repository for every candidate, then imports
`harbor_wrapper.py:WrappedAgent` from that candidate. The wrapper resolves
`src/harbor` inside the candidate copy, so measurements always exercise the
proposed code rather than an installed Harbor package already cached by the
evaluator process.

## Purpose

This agent exists to provide a reproducible baseline for realistic, open-ended
CLI and systems tasks. It takes a task description and autonomously modifies the
canonical task environment to produce the expected files and state.

Because Harbor's task verifier validates outputs objectively, the agent must
produce correct, verifiable results rather than plausible-looking answers.

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

## Model

- **Family/size:** Claude Opus 4.8 (frontier)
- **LiteLLM model name:** `openai/azure/anthropic/claude-opus-4-8`
- **Inference Hub model id:** `azure/anthropic/claude-opus-4-8`
- **API base:** `https://inference-api.nvidia.com/v1`
- **Auth:** `INFERENCE_API_KEY` bearer token, mapped by the target-local wrapper
- **Why this choice:** Strong frontier reasoning and coding performance for
  long-horizon terminal tasks; streaming reduces the cost of incremental output
  without changing the model or benchmark contract.
- **Deployment:** Cloud (NVIDIA Inference Hub, OpenAI-compatible endpoint)

## Framework

The baseline is Harbor's `Terminus2` structured-action loop with the LiteLLM
backend. Candidate changes may tune its prompts, parsing, streaming behavior,
or inference settings, but must preserve the Harbor wrapper contract and ATIF
trajectory production.

## Harness

Harbor imports `harbor_wrapper.py:WrappedAgent`, a subclass of `Terminus2`.
The wrapper imports Terminus-2 from the copied candidate source tree and
pins this experiment's model, endpoint, and streaming settings. It also
publishes Harbor's canonical `/logs/agent/trajectory.json` as
`/app/traces/trajectory.atif.json`. This keeps the adaptation local to this
target while satisfying Experimentalist's existing ATIF artifact contract.
Harbor still owns the agent setup, terminal session, model connection, and
canonical trajectory production.

Invocation:
```bash
INFERENCE_API_KEY=<key> \
uv run harbor run -c <job.yaml>
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

## Success Criteria

- **Task completion**: Harbor's verifier reports reward `1`.
- **Correctness**: Output files in `/app/` match expected content (exact hash, string match, or tolerance check depending on task).
- **Robustness**: The agent recovers from package installation failures, compilation errors, and wrong-output first attempts without manual intervention.
- **Efficiency**: Task solved within the 840 s harness timeout; overly long compilations or training runs must be detected and shortened.

## Evaluation Setup

Evaluated on immutable train, validation, and held-out test subsets of canonical
`terminal-bench/terminal-bench-2-1@6`. Harbor starts the task's unmodified
environment and runs its canonical verifier.

Baseline reference: oracle scripts at `solution/solve.sh` demonstrate the expected solution path.

Manual spot-checks use Harbor with `harbor_wrapper.py:WrappedAgent`.
Experimentalist runs require independent copied train and validation splits;
`optimizer.example.yaml` is intentionally not runnable until those paths are
chosen.

## Change Scope

- Terminus prompts and parsers: **allowed**
- Terminus2-local streaming and completion handling: **allowed**
- Shared Harbor LLM adapters and other agent implementations: **not optimization levers**
- Model and inference parameters: **allowed** (within the NVIDIA inference gateway catalog)
- Harbor runner/bootstrap and task data: **not optimization levers**
- Task data (`tests/`, `solution/`): **allowed only via oracle fix PRs** — changes here affect benchmark integrity
- Spec itself: **not allowed** (spec is the contract; only the developer edits it)

## Signals

Priority signals:
- Mean reward across terminal-bench-ii train and validation sets (target: >0.80).
- Per-category breakdown (systems, ML, security, etc.) to identify weak spots.
- Rate of tasks that time out vs. fail on incorrect output — distinguishes speed problems from reasoning problems.
- Number of terminal actions per task as a proxy for efficiency.

Ignore:
- Individual task failures in isolation — single-task debugging belongs in oracle fix PRs, not agent tuning.
- Latency outside benchmark runs.

## Open Questions

- Whether a larger model meaningfully improves reward on the hard task tail
  enough to justify its latency cost.
- Optimal maximum-turn limit for preventing runaway spending without truncating
  successful tasks.
- Whether streaming reduces tokens and latency without changing valid action
  parsing or benchmark reward.
- Whether task-category-specific system prompt variations (e.g., extra ML hints for PyTorch tasks) improve recall or just add complexity.
