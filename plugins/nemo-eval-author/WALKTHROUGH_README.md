<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Eval Author walkthrough (rho-agent)

End-to-end demo: **audit → close gaps → verify**, using a local workspace and bundled Harbor tasks. No external fixtures repo.

**Requires Docker Desktop 4.86.0+ on macOS** for sandboxed Harbor trials.

## Before you start

Required for both automatic and manual walkthrough paths:

```bash
source plugins/nemo-eval-author/walkthrough/env
```

## Quick start (automatic)

```bash
uv run \
  --with-requirements plugins/nemo-eval-author/walkthrough/quick-start-cli/requirements.txt \
  --with pyyaml \
  python plugins/nemo-eval-author/walkthrough/quick-start-cli/cli.py \
  --agent=cursor \
  --workspace tmp/rho-agent-walkthrough
```

- Use `--agent=claude` for Claude Code.

## What you should see

- **Ethos + audit** — `tmp/rho-agent-walkthrough/agents/rho-agent-ethos/ETHOS.md` and `.eval-author/audit.md` exist; audit validates.
- **Baseline run** — bundled `task-0` covers `write`, leaves other tools uncovered.
- **Gap tasks** — agent closes every actionable gap; scaffolds Harbor drafts, oracle passes, rho-agent trials run.
- **Verify** — `task_pipeline.py verify --target <tool>` returns `"accepted": true` for each closed gap.

## Manual walkthrough

### 1. Workspace

```bash
mkdir -p tmp/rho-agent-walkthrough

git clone https://github.com/smith-nathanh/rho-agent.git tmp/rho-agent-walkthrough/rho-agent
git -C tmp/rho-agent-walkthrough/rho-agent checkout "$RHO_REVISION"

cp plugins/nemo-eval-author/walkthrough/rho-agent/rho_harbor_agent.py tmp/rho-agent-walkthrough/
cp plugins/nemo-eval-author/walkthrough/rho-agent/rho_atif_compat.py tmp/rho-agent-walkthrough/
```

The pinned rho-agent checkout gives nemo-ethos source to explore.

Bundled Harbor input is under `walkthrough/assets/rho-agent/` (`task-0/` and `baseline-job.yaml`):

```bash
mkdir -p tmp/rho-agent-walkthrough/.eval-author/sandbox
cp -r plugins/nemo-eval-author/walkthrough/assets/rho-agent/task-0 \
  tmp/rho-agent-walkthrough/.eval-author/sandbox/
cp plugins/nemo-eval-author/walkthrough/assets/rho-agent/baseline-job.yaml \
  tmp/rho-agent-walkthrough/.eval-author/
chmod +x tmp/rho-agent-walkthrough/.eval-author/sandbox/task-0/tests/test.sh \
  tmp/rho-agent-walkthrough/.eval-author/sandbox/task-0/solution/solve.sh
```

Everything else (ethos, audit, gap tasks, measurements) is created by the agent.

### 2. Sandbox (recommended)

Agent image — build locally to increase rho-agent sandboxing

```bash
bash plugins/nemo-eval-author/walkthrough/rho-agent/build_agent_image.sh
```

Details: [`walkthrough/rho-agent/SANDBOX.md`](walkthrough/rho-agent/SANDBOX.md)

Check egress before a long run (`"supported": true` means Harbor can enforce the sandbox network policy on this daemon):

```bash
uv run --with pyyaml --with harbor \
  plugins/nemo-eval-author/walkthrough/rho-agent/prepare_sandbox.py check-egress
```

See [`walkthrough/rho-agent/SANDBOX.md`](walkthrough/rho-agent/SANDBOX.md).

Legacy unrestricted trials: `RHO_HARBOR_ALLOW_RUNTIME_INSTALL=1`.

### 3. Run with a coding agent

Run these prompts in your coding agent in this repo.

**Create ETHOS.md**

```text
Use nemo-ethos skill to create ETHOS.md for `tmp/rho-agent-walkthrough/rho-agent`. Write the local file to `tmp/rho-agent-walkthrough/agents/rho-agent-ethos/ETHOS.md` only. Don't upload to Filesets.
```

**Eval coverage gaps:**

```text
Use eval-author skill to close eval coverage gaps for tmp/rho-agent-walkthrough/.
```

See section 4 for the skill/script steps eval-author runs.

### 4. What the agent does (reference)

Example path for closing the `read` gap:

| # | Action | Skill / step |
|---|--------|--------------|
| 1 | Write local `tmp/rho-agent-walkthrough/agents/rho-agent-ethos/ETHOS.md` (when missing) | [`nemo-ethos`](../../packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-ethos/SKILL.md); explore `rho-agent/`; do not upload to Filesets |
| 2 | Draft `.eval-author/audit-items.yaml` from ETHOS tools | [`eval-author-audit`](skills/eval-author-audit/SKILL.md) Step 1 |
| 3 | `generate.py` → `.eval-author/audit.md`; `validate.py` passes | `eval-author-audit` Steps 2–3 |
| 4 | `harbor jobs start -c .eval-author/baseline-job.yaml`; measure trials; `report.py` → `.eval-author/audit-coverage-report.json` (`write` covered, `read` uncovered) | `eval-author-audit` Steps 4–5 |
| 5 | `task_pipeline.py select` → actionable `read`, `task_slug: cover-read` | [`eval-author-task-create`](skills/eval-author-task-create/SKILL.md) Step 1 |
| 6 | Write `.eval-author/proposals/cover-read-instruction.md` | `eval-author-task-create` Step 2 |
| 7 | `scaffold` and complete `.eval-author/task-drafts/cover-read/` | `eval-author-task-create` Step 3 |
| 8 | `harbor run -p …/cover-read -a oracle` → reward **1.0** | `eval-author-task-create` Step 4 |
| 9 | Two rho-agent Harbor trials | `eval-author-task-create` Step 5 |
| 10 | `measure.py` + `report.py` per trial under `.eval-author/task-measurements/cover-read/repeat-{1,2}/` | `eval-author-audit` Step 4 + `eval-author-task-create` Step 6 |
| 11 | `task_pipeline.py verify --target read` → `"accepted": true` | `eval-author-task-create` Step 7 |
| 12 | Re-aggregate coverage; repeat for next actionable tool | `eval-author` gap-closing loop → `eval-author-audit` Step 5 |

### 5. Done when

- After audit generation: `.eval-author/audit.md` passes `validate.py`
- After baseline `task-0`: `.eval-author/audit-coverage-report.json` shows `write` covered and at least one other tool uncovered
- For each actionable tool gap: `.eval-author/task-drafts/<task-slug>/` passes oracle with reward 1.0, two repeats under `.eval-author/task-measurements/<task-slug>/`, and `task_pipeline.py verify --target <tool>` returns `"accepted": true`
- After gap closing: `.eval-author/audit-coverage-report.json` lists every measured tool as covered
