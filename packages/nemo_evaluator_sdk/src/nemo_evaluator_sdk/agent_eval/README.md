# Agent-Eval Benchmark Adapters

`AgentEvalBenchmark` adapters turn datasets into SDK-native `AgentEvalTask` values, optional recorded `AgentEvalAttempt` values, metrics, metadata, and optional custom reports. The ProfBench example loads those values through an adapter, then calls `AgentEvaluator.run()` directly.

## ProfBench Examples

Runnable ProfBench examples live in [`examples/profbench/examples.py`](../../../examples/profbench/examples.py):

- `run_offline_profbench_adapter_smoke()`: scores ProfBench's bundled recorded attempts without live model credentials.
- `run_docker_sandbox_profbench_live_candidate_smoke()`: generates fresh attempts with Docker-backed Codex, then scores them with a live judge.
- `run_local_codex_profbench_live_candidate_smoke()`: generates fresh attempts with host `codex exec`, then scores them with a live judge.

Run the examples from the repository root:

```bash
uv run --frozen python -m packages.nemo_evaluator_sdk.examples.profbench.examples offline
```

```bash
NVIDIA_API_KEY=... \
uv run --frozen --package nemo-evaluator-sdk --extra agent-runtimes \
  python -m packages.nemo_evaluator_sdk.examples.profbench.examples docker --agent-model gpt-5.4
```

```bash
NVIDIA_API_KEY=... \
uv run --frozen python -m packages.nemo_evaluator_sdk.examples.profbench.examples local --agent-model gpt-5.4
```

The offline command scores recorded ProfBench attempts, so it does not require live model credentials. For the `docker` command, `OPENAI_API_KEY` is optional: when it is set to an OpenAI Platform secret key (`sk-...`), the example uses SDK Docker sandbox mode; when it is missing or contains an OAuth-style Codex token, it falls back to the Docker CLI Codex path that mounts local Codex auth into the container. `NVIDIA_API_KEY` is still required for the live ProfBench judge. All three commands write under a generated run directory:

```text
env/profbench-results/
  20260608_162200_28290_40da8e/
    evidence/
      profbench-dataset.jsonl
    report.html
    sdk-report.html
```

## Execution Shapes

The evaluator's inputs determine the execution shape:

- `attempts`: score recorded attempts without running a live target.
- `target`: generate fresh attempts from a model, agent, or `AgentAttemptRuntime`, then score those attempts.

Minimal adapter shape:

```python
from pathlib import Path

from nemo_evaluator_sdk.agent_eval import (
    AgentEvalAttempt,
    AgentEvalBenchmarkBundle,
    AgentEvalBenchmarkLoadConfig,
    AgentEvalTask,
    AgentOutput,
)


class MyBenchmark:
    name = "my-benchmark"

    def load(self, config: AgentEvalBenchmarkLoadConfig) -> AgentEvalBenchmarkBundle:
        source = Path(config.source or "data/my-dataset.jsonl")
        tasks = [
            AgentEvalTask(
                id="task-1",
                intent=source.read_text(encoding="utf-8"),
                inputs={"prompt": "Answer the task."},
                metrics=[MyMetric()],
            )
        ]

        return AgentEvalBenchmarkBundle(
            tasks=tasks,
            attempts=[
                AgentEvalAttempt(
                    id="attempt-1",
                    task_id="task-1",
                    output=AgentOutput(text="Recorded answer."),
                )
            ],
            metadata={"benchmark": self.name},
        )


def benchmark_factory() -> MyBenchmark:
    return MyBenchmark()
```

Benchmark-specific constructor settings should live in the class or factory. Generic callers pass `source`, `limit`, and `evidence_dir`. If a benchmark needs custom HTML output, it can also implement `write_reports(result, output_dir)`.

## Code Sandbox Invocation

For live candidate generation, pass a model, agent, or `AgentAttemptRuntime` as the `target` to `AgentEvaluator.run()`. Codex runtimes live under `nemo_evaluator_sdk.agent_eval.runtimes.codex.runtime`.

Runtime and credential behavior:

- `resolve_codex_target(runtime=RuntimeChoice.DOCKER, ...)` prefers `DockerSandboxAgentRuntime` when `OPENAI_API_KEY` looks like an OpenAI Platform secret key (`sk-...`). Model calls are made by the OpenAI Agents SDK from the host process; the Docker container is the execution workspace and `~/.codex/auth.json` is not mounted.
- Docker mode falls back to Dockerized Codex CLI when `OPENAI_API_KEY` is missing or is a Codex OAuth token. It mounts `~/.codex/auth.json` read-only into a `node:22-alpine` container and runs `npx -y @openai/codex@0.137.0 exec ...`; Codex OAuth tokens are not converted into API keys. Because Docker is the isolation boundary, this path runs Codex with its nested shell-command sandbox disabled to avoid `bwrap` user-namespace failures inside the container.
- `resolve_codex_target(runtime=RuntimeChoice.LOCAL, ...)` uses host `codex exec` from `PATH`, so it relies on local Codex login/auth. It passes `--ignore-user-config` so benchmark runs do not inherit `$CODEX_HOME/config.toml` MCP servers, plugins, approval settings, or other user-specific tool configuration. No Docker containers are expected in this mode.

Install the optional runtime extra for SDK Docker mode:

```bash
uv sync --frozen --package nemo-evaluator-sdk --extra agent-runtimes
```

Run the live-candidate ProfBench example through Docker-backed Codex:

```bash
NVIDIA_API_KEY=... \
uv run --frozen --package nemo-evaluator-sdk --extra agent-runtimes \
  python -m packages.nemo_evaluator_sdk.examples.profbench.examples docker
```

With an OpenAI Platform `OPENAI_API_KEY` (`sk-...`), this uses SDK Docker sandbox mode and writes sandbox attempt evidence under:

```text
env/profbench-results/20260608_162200_28290_40da8e/
  agent-runtime/20260608_162200_28290_40da8e/<task-id>/
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

- If `OPENAI_API_KEY` is set to an OpenAI Platform secret key (`sk-...`), `DockerSandboxAgentRuntime` uses the OpenAI Agents SDK `SandboxAgent`; model calls are made from the host process and use `OPENAI_API_KEY`.
- If `OPENAI_API_KEY` is missing or is an OAuth-style Codex token, the example falls back to `CodexDockerCliAgentRuntime`, mounts local `~/.codex/auth.json` read-only, and runs Codex CLI inside the container.
- In SDK Docker sandbox mode, the Docker container is an execution sandbox for task workspace/files. It does not receive API keys unless you explicitly mount or write them into the task workspace later.
- `ProfBenchModelJudge` uses the regular NeMo Evaluator SDK model path. In the example above, `SecretRef(root="NVIDIA_API_KEY")` resolves the judge key from the local `NVIDIA_API_KEY` environment variable.

Run the live-candidate ProfBench example through local Codex:

```bash
NVIDIA_API_KEY=... \
uv run --frozen python -m packages.nemo_evaluator_sdk.examples.profbench.examples local --agent-model gpt-5.5
```

This path uses host `codex exec`, local Codex auth, and no Docker container. It passes `--ignore-user-config` so benchmark runs do not inherit `$CODEX_HOME/config.toml` MCP servers, plugins, approval settings, or other user-specific Codex tool configuration. Omit `--agent-model` to use the local Codex CLI default model.

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

## ProfBench Execution Paths

ProfBench supports the same three evaluation paths through `ProfBenchAgentEvalBenchmark`, `AgentEvalBenchmarkLoadConfig`, and `AgentEvaluator.run()`. They differ along two axes: **whose answers are scored** and **how rubrics are decided**.

## Comparison

| | **Baseline** | **Live judge** | **Live candidate** |
|---|---|---|---|
| **Answers** | Pre-recorded in the dataset (`o3`, `r1-0528`, `grok4`) | Same pre-recorded answers | **New** answers from the supplied target |
| **Rubric scoring** | Dataset labels (`{model}_fulfilment` in JSONL) | Live LLM judge per criterion | Live LLM judge per criterion |
| **API / cost** | None (offline) | Judge calls only | Inference + judge calls |
| **Evaluator input** | `attempts` | `attempts` | `target` |

## 1. Baseline - reproduce published scores

```python
benchmark = ProfBenchAgentEvalBenchmark()
bundle = benchmark.load(
    AgentEvalBenchmarkLoadConfig(
        limit=limit,
        evidence_dir=output_dir / "evidence",
    )
)
result = await AgentEvaluator().run(
    tasks=bundle.tasks,
    attempts=bundle.attempts,
    config=AgentEvalRunConfig(output_dir=output_dir, run_id="profbench-baseline"),
)
reports = benchmark.write_reports(result, output_dir)
```

- `ProfBenchAgentEvalBenchmark` with **no judge** and `include_cached_fulfilments=True` (default).
- Each attempt gets `profbench_fulfilments` from the dataset; `ProfBenchRubricMetric` uses those (`score_source: "dataset_label"`) and never calls a judge.
- Fast, deterministic check that loading and scoring work without credentials.

## 2. Live judge - same text, new judge

```python
benchmark = ProfBenchAgentEvalBenchmark(
    judge_factory=lambda: ProfBenchModelJudge(model=judge_model),
    include_cached_fulfilments=False,
    score_source="live_judge",
)
bundle = benchmark.load(
    AgentEvalBenchmarkLoadConfig(
        limit=limit,
        evidence_dir=output_dir / "evidence",
    )
)
result = await AgentEvaluator().run(
    tasks=bundle.tasks,
    attempts=bundle.attempts,
    config=AgentEvalRunConfig(output_dir=output_dir, run_id="profbench-live-judge"),
)
reports = benchmark.write_reports(result, output_dir)
```

- Still scores the **bundled** baseline responses via stored attempts.
- `include_cached_fulfilments=False` drops precomputed labels so every criterion goes through `ProfBenchModelJudge` (`score_source: "judge"`).
- Useful to validate your judge model/setup against fixed candidate outputs, without running the candidate model.

## 3. Live candidate - generate + judge

```python
params = RunConfigOnlineModel(
    parallelism=2,
    inference=InferenceParams(temperature=0.0, max_tokens=4096),
)
benchmark = ProfBenchAgentEvalBenchmark(
    judge_factory=lambda: ProfBenchModelJudge(model=judge_model),
    score_source="fresh_candidate_and_live_judge",
)
bundle = benchmark.load(
    AgentEvalBenchmarkLoadConfig(
        limit=limit,
        evidence_dir=output_dir / "evidence",
    )
)
result = await AgentEvaluator().run(
    tasks=bundle.tasks,
    target=evaluated_model,
    config=AgentEvalRunConfig(output_dir=output_dir, run_id="profbench-live-candidate", params=params),
)
reports = benchmark.write_reports(result, output_dir)
```

- The evaluator calls the **target** model (`RunConfigOnlineModel`, parallelism 2, `temperature=0`, `max_tokens=4096`) to produce answers, then scores them with the same live judge.
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
