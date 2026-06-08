# Tool Calling Evaluation

You are in the NeMo Platform repo at `/app`. MCP tools are not available.
Use shell commands and repo files only.

Start with the repo skill:

```bash
sed -n '1,240p' /app/plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/SKILL.md
```

Important alignment notes:

- Use `/app/.venv/bin/nemo`, not `nmp`.
- Do not use the legacy generated `nemo evaluation ...` command group.
- The plugin CLI surface is `nemo evaluator ...`.
- Use `nemo evaluator metric-types tool-calling` or `nemo evaluator evaluate explain` for the current schema.
- If persistent metric or metric-job resources are not exposed as CLI subcommands, use the installed Python SDK client from `/app/.venv/bin/python`. The verifier checks platform state through `nemo_platform.NeMoPlatform`.

## Task

Set up and run a BFCL-style tool-calling evaluation in workspace `tool-calling-eval-workspace`.

1. Create workspace `tool-calling-eval-workspace`.
2. Create a JSONL dataset and upload it to fileset `tool-calling-dataset`.
3. Each row must include:
   - `messages`: user message array
   - `tools`: OpenAI function tool definitions
   - `expected_tool_calls`: expected function calls
   - `response`: simulated OpenAI chat completion response containing `choices[0].message.tool_calls`
4. Include at least three rows:
   - one exact match
   - one wrong function name
   - one correct function name with wrong arguments
5. Create a `tool-calling` metric named `tool-calling-accuracy` whose reference template reads `expected_tool_calls`.
6. Run a synchronous evaluation against 2-3 inline rows and verify:
   - `function_name_accuracy` is reported
   - `function_name_and_args_accuracy` is reported
   - exact matches score `1.0`
   - wrong function names score `0.0`
   - correct name/wrong args scores `1.0` for name and `0.0` for name+args
7. Create a metric job referencing `tool-calling-accuracy` and `tool-calling-dataset`; it may remain in `created` status.
8. Retrieve or list the job to confirm it exists.

## Fast Path

For inline evaluation, prefer:

```bash
/app/.venv/bin/nemo evaluator evaluate run --spec-file <spec.json>
```

For persistent resources that are not exposed in the CLI, use the SDK:

- `from nemo_platform import NeMoPlatform`
- connect to `http://localhost:8080`
- use `client.workspaces`, `client.files.filesets`, `client.files`, `client.evaluation.metrics`, and `client.evaluation.metric_jobs`

Keep schema discovery focused on `nemo evaluator metric-types tool-calling`, `nemo evaluator evaluate explain`, the Evaluator plugin skill, and installed SDK type docs.

## Success Criteria

The task is complete when:

- workspace `tool-calling-eval-workspace` exists
- fileset `tool-calling-dataset` exists and contains uploaded data
- metric `tool-calling-accuracy` exists and is type `tool-calling`
- synchronous evaluation produced `function_name_accuracy` and `function_name_and_args_accuracy`
- a metric job exists and references the metric/dataset
