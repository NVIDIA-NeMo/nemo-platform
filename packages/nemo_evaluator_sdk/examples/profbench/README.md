# ProfBench Agent-Eval Example

Run the example from the repository root:

```bash
python -m packages.nemo_evaluator_sdk.examples.profbench.runner --output-dir env/profbench-results --limit=1
```

Each invocation creates one run directory under `--output-dir`, then writes each enabled runner mode under that run:

```text
env/profbench-results/
  20260604_161501_61063_eb0cf0/
    baseline/
      evidence/
        profbench-dataset.jsonl
      report.html
      sdk-report.html
    live-judge/
      evidence/
        profbench-dataset.jsonl
        judge-*.json
      report.html
      sdk-report.html
    live-candidate/
      evidence/
        profbench-dataset.jsonl
        judge-*.json
      report.html
      sdk-report.html
```

Live paths are enabled by default and require API access through the configured model settings. Pass `--no-run-live-judge` or `--no-run-live-candidate` to skip either live path.

## Code Sandbox Invocation

The CLI runner above uses the configured chat-completions model directly for `live-candidate`. To run ProfBench with a Codex-style candidate agent, pass `--agent codex`. Docker is the default Codex runtime preference: it uses SDK Docker when `OPENAI_API_KEY` is an OpenAI Platform secret key, and otherwise starts a lightweight Docker container that runs Codex CLI with your local Codex auth mounted read-only.

```bash
python -m packages.nemo_evaluator_sdk.examples.profbench.runner \
  --output-dir env/profbench-results \
  --limit=1 \
  --agent codex \
  --agent-model gpt-5.4
```

List locally visible Codex model slugs before choosing `--agent-model`:

```bash
python -m packages.nemo_evaluator_sdk.examples.profbench.runner --agent codex --list-agent-models
```

Runtime and credential behavior:

- `--agent codex --runtime docker` prefers `DockerSandboxAgentRuntime` when `OPENAI_API_KEY` looks like an OpenAI Platform secret key (`sk-...`). Model calls are made by the OpenAI Agents SDK from the host process; the Docker container is the execution workspace and `~/.codex/auth.json` is not mounted.
- `--agent codex --runtime docker` falls back to Dockerized Codex CLI when `OPENAI_API_KEY` is missing or is a Codex OAuth token. It mounts `~/.codex/auth.json` read-only into a `node:22-alpine` container and runs `npx -y @openai/codex@0.137.0 exec ...`; Codex OAuth tokens are not converted into API keys. Because Docker is the isolation boundary, this path runs Codex with its nested shell-command sandbox disabled to avoid `bwrap` user-namespace failures inside the container.
- `--agent codex --runtime local` always uses host `codex exec` from `PATH`, so it relies on your local Codex login/auth. It passes `--ignore-user-config` so benchmark runs do not inherit `$CODEX_HOME/config.toml` MCP servers, plugins, approval settings, or other user-specific tool configuration. No Docker containers are expected in this mode.
- The live ProfBench judge still uses the regular NeMo Evaluator SDK model settings, so the default judge path still needs `NVIDIA_API_KEY` unless you override the judge model and secret settings.
- If `--agent-model` is omitted, SDK Docker uses the documented default Codex sandbox model; Dockerized/local CLI uses the default model in your Codex config.

Install the optional runtime extra for SDK Docker mode:

```bash
uv sync --frozen --package nemo-evaluator-sdk --extra agent-runtimes
```

The lower-level SDK equivalent is:

```bash
OPENAI_API_KEY=... NVIDIA_API_KEY=... \
uv run --frozen --package nemo-evaluator-sdk --extra agent-runtimes python - <<'PY'
import asyncio
from pathlib import Path

from nemo_evaluator_sdk.agent_eval import AgentEvalRunConfig, AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.docker_sandbox import DockerSandboxAgentRuntime
from nemo_evaluator_sdk.values import Model, SecretRef

from packages.nemo_evaluator_sdk.examples.profbench.dashboard import write_example_dashboards
from packages.nemo_evaluator_sdk.examples.profbench.profbench import (
    PROFBENCH_DATASET_URL,
    ProfBenchModelJudge,
    load_profbench,
)


async def main() -> None:
    output_dir = Path("env/profbench-results/code-sandbox-smoke")
    judge_model = Model(
        url="https://integrate.api.nvidia.com/v1/chat/completions",
        name="nvidia/nemotron-3-nano-30b-a3b",
        api_key_secret=SecretRef(root="NVIDIA_API_KEY"),
    )
    benchmark = load_profbench(
        PROFBENCH_DATASET_URL,
        limit=1,
        judge=ProfBenchModelJudge(model=judge_model),
        evidence_dir=output_dir / "evidence",
        include_cached_fulfilments=False,
    )
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        target=DockerSandboxAgentRuntime(model="gpt-4.1-mini", timeout_s=180),
        config=AgentEvalRunConfig(
            output_dir=output_dir,
            run_id="profbench-code-sandbox-smoke",
            parallelism=1,
            benchmark={**benchmark.metadata, "score_source": "docker_sandbox_and_live_judge"},
            write_dashboard=False,
        ),
    )
    sdk_dashboard_path, dashboard_path = write_example_dashboards(result, output_dir)
    print(f"SDK dashboard: {sdk_dashboard_path}")
    print(f"Dashboard: {dashboard_path}")


asyncio.run(main())
PY
```

This writes the sandbox attempt evidence under:

```text
env/profbench-results/code-sandbox-smoke/
  agent-runtime/profbench-code-sandbox-smoke/<task-id>/
    final_output.txt
    run_items.json
    raw_responses.json
    workspace.tar
    final_state/
  evidence/
    profbench-dataset.jsonl
    judge-*.json
  report.html
  sdk-report.html
```

Credential flow:

- `DockerSandboxAgentRuntime` uses the OpenAI Agents SDK `SandboxAgent`; model calls are made from the host process and use `OPENAI_API_KEY`.
- The Docker container is an execution sandbox for task workspace/files. It does not receive your API keys unless you explicitly mount or write them into the task workspace later.
- `ProfBenchModelJudge` uses the regular NeMo Evaluator SDK model path. In the example above, `SecretRef(root="NVIDIA_API_KEY")` resolves the judge key from the local `NVIDIA_API_KEY` environment variable.
- For the normal ProfBench CLI, the evaluated and judge models default to NVIDIA NIM. Configure them with `NEMO_EVALUATOR_PROFBENCH_EVALUATED_MODEL_URL`, `NEMO_EVALUATOR_PROFBENCH_EVALUATED_MODEL`, `NEMO_EVALUATOR_PROFBENCH_JUDGE_MODEL_URL`, and `NEMO_EVALUATOR_PROFBENCH_JUDGE_MODEL`. The API-key environment variable name defaults to `NVIDIA_API_KEY` and can be changed with `NMP_EVALUATOR_DEFAULT_API_KEY_SECRET`.

## Domain Model

| Concept | Meaning |
| :---- | :---- |
| Task | The unit of work being evaluated. It contains intent, inputs, metrics, and optional views. |
| Benchmark | An immutable collection of agent evaluation tasks. |
| Run | One agent evaluated against one benchmark. |
| Attempt | One agent execution or imported trace-derived attempt for one task. |
| Evidence | Final output, final state, traces, logs, measurements, labels, and review artifacts captured for an attempt. |
| Metric | An SDK `Metric` implementation that consumes `MetricInput` and emits outputs declared by `output_spec()`. |
| Result | Metric outputs and diagnostics produced for one attempt and one metric. |

The key relationship is simple: benchmarks list tasks, tasks declare metrics, runs contain attempts, attempts have evidence, and results score attempts with metrics. Ordered task refs can live on benchmarks. Ordered metric refs can live on tasks.

Use case → user inputs and expected outputs →(mapped to) tasks → metrics

## Runner Types

`run_examples` always runs the **baseline** path; the other two run by default and can be disabled with `--no-run-live-judge` and `--no-run-live-candidate`. They differ along two axes: **whose answers are scored** and **how rubrics are decided**.

## Comparison

| | **Baseline** | **Live judge** | **Live candidate** |
|---|---|---|---|
| **Answers** | Pre-recorded in the dataset (`o3`, `r1-0528`, `grok4`) | Same pre-recorded answers | **New** answers from `_evaluated_model()` |
| **Rubric scoring** | Dataset labels (`{model}_fulfilment` in JSONL) | Live LLM judge per criterion | Live LLM judge per criterion |
| **API / cost** | None (offline) | Judge calls only | Inference + judge calls |
| **Default in `run_examples`** | Always | Enabled by default (`--no-run-live-judge` disables) | Enabled by default (`--no-run-live-candidate` disables) |

## 1. `run_profbench_baseline_example` - reproduce published scores

```python
async def run_profbench_baseline_example(
    *,
    limit: int | None,
    output_root: str | Path | None = None,
    run_instance_id: str | None = None,
) -> None:
    """Score the ProfBench baseline model responses bundled in the dataset."""
    ...
    output_dir = _profbench_output_dir(output_root, run_instance_id, "baseline")
    benchmark = load_profbench(_profbench_source(), limit=limit, evidence_dir=output_dir / "evidence")
    result = await AgentEvaluator().run(
        tasks=benchmark.tasks,
        attempts=benchmark.attempts,
        ...
    )
```

- `load_profbench` with **no judge** and `include_cached_fulfilments=True` (default).
- Each attempt gets `profbench_fulfilments` from the dataset; `ProfBenchRubricMetric` uses those (`score_source: "dataset_label"`) and never calls a judge.
- Fast, deterministic check that loading and scoring work without credentials.

## 2. `run_profbench_live_judge_example` - same text, new judge

```python
benchmark = load_profbench(
    _profbench_source(),
    limit=limit,
    judge=ProfBenchModelJudge(model=judge_model),
    evidence_dir=output_dir / "evidence",
    include_cached_fulfilments=False,
)

result = await AgentEvaluator().run(
    tasks=benchmark.tasks,
    attempts=benchmark.attempts,
    ...
)
```

- Still scores the **bundled** baseline responses via `attempts=benchmark.attempts`.
- `include_cached_fulfilments=False` drops precomputed labels so every criterion goes through `ProfBenchModelJudge` (`score_source: "judge"`).
- Useful to validate your judge model/setup against fixed candidate outputs, without running the candidate model.

## 3. `run_profbench_live_candidate_example` - generate + judge

```python
evaluated_model = _evaluated_model()
params = RunConfigOnlineModel(
    parallelism=2,
    inference=InferenceParams(temperature=0.0, max_tokens=4096),
)
result = await AgentEvaluator().run(
    tasks=benchmark.tasks,
    target=evaluated_model,
    config=AgentEvalRunConfig(
        output_dir=output_dir,
        params=params,
        benchmark={**benchmark.metadata, "score_source": "fresh_candidate_and_live_judge"},
        ...
    ),
)
```

- **No** `attempts=` - the evaluator calls the **target** model (`RunConfigOnlineModel`, parallelism 2, `temperature=0`, `max_tokens=4096`) to produce answers, then scores them with the same live judge.
- Full "evaluate my model on ProfBench" path: new responses + live rubric judging.
- Most expensive; needs inference and judge API access.

## Scoring Logic

All three use `ProfBenchRubricMetric`. Cached labels win when present; otherwise a judge is required:

```python
if criterion.id in fulfilments:
    fulfilled = fulfilments[criterion.id]
else:
    if self.judge is None:
        raise ValueError("ProfBench candidate scoring requires a judge when dataset labels are absent")
    score_source = "judge"
```

- **Baseline**: fulfilments always present, so it uses dataset labels only.
- **Live judge / live candidate**: fulfilments are stripped, so the judge runs on every criterion; candidate path additionally supplies fresh `output_text` from the target model instead of dataset response fields.
