# Evaluator ASE custom grader PoC

This directory contains a proof-of-concept migration of Evaluator
`tests/agentic-use` tasks into native Harbor tasks that can be run by
`astra-skill-eval` with `aces_plus_custom` grading.

## Included tasks

The branch contains all migrated Evaluator Harbor tasks from the local port:

- `evaluator-academic-benchmark-cli`
- `evaluator-academic-benchmark-cli-easy`
- `evaluator-llm-judge-cli`
- `evaluator-llm-judge-cli-easy`
- `evaluator-simple-job-cli`
- `evaluator-simple-job-cli-easy`
- `evaluator-standalone-sdk-agent-target`
- `evaluator-standalone-sdk-simple-exact-match`
- `evaluator-standalone-sdk-surface-adherence-metric`
- `evaluator-standalone-sdk-surface-discovery`
- `evaluator-tool-calling-cli`
- `evaluator-zero-config-judge-cli`

Each task has a Harbor-compatible task directory with:

- `instruction.md`: the agent-facing task prompt
- `environment/Dockerfile`: the task container environment
- `tests/grader.py`: the Harbor custom grader entrypoint
- `tests/task.toml`: task-local verifier metadata

The standalone SDK tasks also include:

- `tests/task_metrics.py`: task-specific deterministic Evaluator metrics
- `tests/evaluator_agent_eval/`: the migrated shared Evaluator agent-eval helpers

The CLI-style tasks use the shared `skills/nemo-evaluator-plugin/evals/grader.py`
entrypoint copied into their task test directories.

ASE combines the custom grader scores with the built-in ACES metrics because
`skills/nemo-evaluator-plugin/evals/config.yml` sets:

```yaml
grading:
  mode: aces_plus_custom
```

## Why the shared helper code is copied

The original `agentic-use` tests depend on helper code that is not installed into
the Harbor task containers as a package. For this PoC, the migrated standalone
SDK tasks carry a local copy under `tests/` so the grader is self-contained
inside the container.

## Local Docker run

From the skill root:

```bash
cd /Users/schapman/workspace/nemo-platform/skills/nemo-evaluator-plugin

/Users/schapman/workspace/skill-eval-ci/.venv/bin/astra-skill-eval evaluate \
  . \
  --agent-eval \
  -a claude-code \
  --env-mode docker \
  --n-concurrent 4 \
  --max-agents 1 \
  --timeout-multiplier 4 \
  --results-dir /tmp/ase-evaluator-poc \
  --harbor-keep-jobs
```

Set the usual agent/API credentials before running. The task `task.toml` files
enable internet access because local Docker execution needs the agent to reach
its model endpoint.

`dataset.toml` lists all migrated Evaluator Harbor tasks so the command above
runs the full local migration set with unmodified ASE.

## Proof run

The checked-in report is from the successful local Docker proof run of the four
standalone SDK custom-metric tasks with `aces_plus_custom` grading. It produced:

- 8 Harbor trials with `reward.json`
- 0 Harbor `exception.txt` files
- custom deterministic Evaluator metrics of `1.0` in both with-skill and
  without-skill arms
- ACES overall score `0.7298` with skill and `0.7402` without skill

A static copy of that generated ASE report is checked in at:

```text
proof/aces-plus-custom-report.html
```

The skill lift numbers in that report are proof-of-work for the harness and
grader migration, not a product-quality assessment of the Evaluator skill.
