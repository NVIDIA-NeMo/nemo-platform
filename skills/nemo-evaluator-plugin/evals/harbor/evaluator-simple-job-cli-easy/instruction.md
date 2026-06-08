# Simple Evaluator Metric Job

You are in the NeMo Platform repo at `/app`. MCP tools are not available.
Use shell commands and repo files only.

Start with the repo skill:

```bash
sed -n '1,220p' /app/plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/SKILL.md
```

Important alignment notes:

- Use `/app/.venv/bin/nemo`, not `nmp`.
- Do not use the legacy generated `nemo evaluation ...` command group.
- The plugin CLI surface is `nemo evaluator ...`.
- Use `nemo evaluator evaluate explain` or `nemo evaluator metric-types` for current metric schema details.
- If persistent metric or metric-job resources are not exposed as CLI subcommands, use the installed Python SDK client from `/app/.venv/bin/python`. The verifier checks platform state through `nemo_platform.NeMoPlatform`.

## Task

Set up a string-check evaluation in workspace `eval-test-workspace`.

1. Create workspace `eval-test-workspace`.
2. Create a JSONL dataset containing `output` and `expected` fields:
   ```jsonl
   {"output": "hello", "expected": "hello"}
   {"output": "world", "expected": "world"}
   {"output": "foo", "expected": "bar"}
   ```
3. Upload the dataset to a fileset named `eval-dataset`.
4. Create a string-check metric that compares `output` to `expected` using an equals operation.
5. Run a synchronous evaluation against small inline rows and verify matching rows score `1.0` and mismatching rows score `0.0`.
6. Create an asynchronous metric evaluation job referencing the metric and `eval-dataset`.
7. Retrieve or list the job to confirm it exists. It may remain in `created` status.

## Fast Path

Prefer current plugin commands for inline evaluation:

```bash
/app/.venv/bin/nemo evaluator evaluate explain
/app/.venv/bin/nemo evaluator evaluate run --spec-file <spec.json>
```

For persistent resources that are not exposed in the CLI, use the SDK:

- `from nemo_platform import NeMoPlatform`
- connect to `http://localhost:8080`
- use `client.workspaces`, `client.files.filesets`, `client.files`, `client.evaluation.metrics`, and `client.evaluation.metric_jobs`

## Success Criteria

The task is complete when:

- workspace `eval-test-workspace` exists
- fileset `eval-dataset` exists and contains uploaded data
- a string-check metric exists in the workspace
- a synchronous evaluation returned scores
- a metric job exists and references the metric/dataset
