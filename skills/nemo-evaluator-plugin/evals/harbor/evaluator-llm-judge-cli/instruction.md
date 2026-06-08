# LLM-as-a-Judge Evaluation

You are in the NeMo Platform repo at `/app`. MCP tools are not available.
Use shell commands and repo files only.

Start with the repo skill:

```bash
sed -n '1,240p' /app/plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/SKILL.md
sed -n '1,220p' /app/plugins/nemo-evaluator/src/nemo_evaluator/skills/evaluator-plugin/references/llm-judge.md
```

Important alignment notes:

- Use `/app/.venv/bin/nemo`, not `nmp`.
- Do not use the legacy generated `nemo evaluation ...` command group.
- The plugin CLI surface is `nemo evaluator ...`.
- Use `nemo evaluator evaluate explain` and `nemo evaluator metric-types llm-judge` for current schema details.
- If persistent metric or metric-job resources are not exposed as CLI subcommands, use the installed Python SDK client from `/app/.venv/bin/python`. The verifier checks platform state through `nemo_platform.NeMoPlatform`.
- For the inference key, use the first non-empty value from `NVIDIA_API_KEY`, `NVIDIA_INFERENCE_KEY`, `OPENAI_API_KEY`, or `ANTHROPIC_API_KEY`. Do not assume `ANTHROPIC_API_KEY` exists.

## Task

Set up and run an LLM-as-a-Judge evaluation in workspace `eval-judge-workspace`.

1. Ensure workspace `eval-judge-workspace` exists.
2. Create or update a platform secret named `nvidia-api-key` using the first available inference key environment variable listed above.
3. Create a JSONL dataset with `input` and `output` fields, including at least one poor-quality response.
4. Upload the dataset to a fileset named `judge-eval-dataset`.
5. Create an `llm-judge` metric named `quality-judge`:
   - model name: `nvidia/openai/gpt-oss-20b`
   - model URL: `https://inference-api.nvidia.com/v1` or the configured IGW proxy URL
   - format: `openai`
   - api key secret: `nvidia-api-key`
   - score name: `relevance`
   - range: 1 to 5
   - JSON parser extracts `relevance`
   - messages-format prompt template asks for JSON output
6. Run a synchronous evaluation against 2-3 inline rows and verify each row has a `relevance` score in `[1, 5]`.
7. Create a metric job referencing `quality-judge` and `judge-eval-dataset`; it may remain in `created` status.
8. Retrieve or list the job to confirm it exists.

## Fast Path

For inline evaluation, prefer:

```bash
/app/.venv/bin/nemo evaluator evaluate run --spec-file <spec.json>
```

For persistent resources that are not exposed in the CLI, use the SDK:

- `from nemo_platform import NeMoPlatform`
- connect to `http://localhost:8080`
- use `client.workspaces`, `client.secrets`, `client.files.filesets`, `client.files`, `client.evaluation.metrics`, and `client.evaluation.metric_jobs`

Keep schema discovery focused on the Evaluator plugin skill, `nemo evaluator evaluate explain`, `nemo evaluator metric-types`, and installed SDK type docs. Avoid broad repo archaeology.

## Success Criteria

The task is complete when:

- fileset `judge-eval-dataset` exists and contains uploaded data
- metric `quality-judge` exists and is type `llm-judge`
- metric config includes the model, `nvidia-api-key`, score, parser, and prompt template above
- synchronous evaluation produced `relevance` scores
- a metric job exists and references `quality-judge`
