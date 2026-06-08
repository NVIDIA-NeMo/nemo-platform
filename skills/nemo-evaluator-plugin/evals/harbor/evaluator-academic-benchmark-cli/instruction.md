# Academic Benchmark Evaluation

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
- If a benchmark resource is not exposed as a first-class CLI subcommand, use the installed Python SDK client from the same virtualenv. The verifier checks platform state through `nemo_platform.NeMoPlatform`.
- Do not spend time searching unrelated `services/*` implementation internals unless the SDK/CLI help is insufficient.

## Task

Create an academic benchmark evaluation job for MMLU.

1. Create a workspace named `benchmark-eval-workspace`.
2. List or retrieve system benchmarks and choose an MMLU benchmark, such as `system/mmlu-instruct`.
3. Create a benchmark evaluation job in `benchmark-eval-workspace` with this model config:
   - URL: `http://localhost:8000/v1`
   - name: `mock-model`
4. Retrieve the job details/status.
5. List benchmark jobs in `benchmark-eval-workspace`.

It is acceptable for the created job to remain in `created` status because the job worker may not be running.

## Fast Path

If `nemo evaluator --help` does not expose benchmark job commands, use `/app/.venv/bin/python` and the installed SDK:

- `from nemo_platform import NeMoPlatform`
- connect to `http://localhost:8080`
- call workspace, benchmark, and benchmark-job resources on `client.evaluation`

Use `dir(client.evaluation)` and SDK method help if needed, but keep the search focused on these resources.

## Success Criteria

The task is complete when:

- workspace `benchmark-eval-workspace` exists
- a benchmark evaluation job exists in that workspace
- the job spec references an MMLU system benchmark
- the job spec includes the model URL/name above
