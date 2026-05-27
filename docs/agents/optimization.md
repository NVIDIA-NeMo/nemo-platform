# Optimize Agents

<a id="agents-optimization"></a>

Use the Agent Optimizer to analyze a deployed agent and act on improvement
suggestions. The optimizer inspects the agent's config, the workspace model
catalog, any prior optimizer snapshots, and optional evaluation baselines,
then writes suggestions you can review from the CLI or hand off to a coding
agent.

This page covers the main path: establish a baseline, generate optimization
suggestions, apply a candidate change to a sibling agent, and review the
evaluation result before promotion.

## What the Optimizer Checks

| Suggestion type | Signal | Result |
|-----------------|--------|--------|
| Model optimization | An agent uses a single frontier model where a smaller model or route split may preserve quality at lower cost | Suggests a model swap or Switchyard random-routing virtual model |
| Skill optimization | The agent uses skills and has an evaluation suite | Suggests running `nemo agents optimize-skills` to improve skill files and keep changes that pass evaluation |
| Prompt optimization | The agent has an optimization config and baseline dataset | Suggests `nemo agents optimize run` for NAT prompt or parameter tuning |
| New model scan | Difference between the current model list and the previous optimizer snapshot | Suggests evaluating or auditing newly available models |

Optimizer state is stored in the `nemo-agent-optimizer` fileset:

- `optimizer_suggestions.jsonl`: one suggestion per line, including applied state.
- `optimizer_snapshot.json`: model and agent names from the latest run.

Security-oriented suggestions such as missing guardrails, PII exposure, or
leaked secrets are covered in [Secure Agents](security.md).

## Prerequisites

Before running the optimizer, make sure you have:

1. Local services running (`nemo services run`).
1. The agents plugin installed. For local development from this repository:
   ```bash
   uv pip install -e packages/nemo_platform_plugin -e plugins/nemo-agents
   ```
1. A workspace with at least one model provider and discovered model entities.
1. At least one deployed platform-managed agent.
1. An evaluation baseline before promoting a candidate agent.

If you need a demo agent, start the platform and create the ReAct example:

```bash
nemo services run
```

In another terminal:

```bash
export NMP_BASE_URL=http://127.0.0.1:8080
cd plugins/nemo-agents

printf '%s' "$NVIDIA_API_KEY" | nemo secrets create ngc-api-key --from-file -
nemo inference providers create nvidia-build \
  --host-url https://integrate.api.nvidia.com \
  --api-key-secret-name ngc-api-key
nemo wait inference provider nvidia-build

nemo agents create \
  --name react-agent \
  --agent-config examples/react-agent/react-agent.yml
nemo agents deploy --agent react-agent
nemo agents deployments wait --agent react-agent
```

The example agent uses `nvidia-nemotron-3-nano-30b-a3b`, so it can produce a
model optimization suggestion when the workspace model catalog contains a
smaller compatible model.

## Optimize with Switchyard Routing

Switchyard is the inference middleware that lets a virtual model split traffic
across multiple backend models. The common optimization pattern is to create a
[virtual model](../run-inference/about.md) with a strong model and a weaker,
cheaper model, then evaluate whether the route split preserves application
quality.

Run `nemo models list` first and replace the placeholders below with model
entity names from your workspace that use the `OPENAI_CHAT` backend format.

=== "CLI"

    The command below creates a virtual model that sends 80% of traffic to the
    strong model and 20% to the weak one.

    ```bash
    nemo inference virtual-models create routed-agent-model \
      --workspace default \
      --models '[
        {"model":"default/<strong-model-entity>","backend_format":"OPENAI_CHAT"},
        {"model":"default/<weak-model-entity>","backend_format":"OPENAI_CHAT"}
      ]' \
      --request-middleware '[{
        "name":"nemo-switchyard",
        "config_type":"random_routing",
        "config":{
          "strong":{"model":"default/<strong-model-entity>"},
          "weak":{"model":"default/<weak-model-entity>"},
          "strong_probability":0.8,
          "enable_stats":false
        }
      }]'
    ```

    Before wiring the virtual model to an agent, smoke-test the route by
    making several minimal chat-completions calls and checking the returned
    model name. The observed split should roughly match `strong_probability`.

=== "Skill"

    Ask your coding agent:

    > Optimize my deployed agent.

    The `agents-optimize` skill picks a deployed agent, establishes an
    evaluation baseline, runs the analysis steps below, and surfaces
    suggestions for you to apply.

    Verify the skill is installed:

    ```bash
    nemo skills show agents-optimize
    ```

    What it does under the hood:

    - Lists deployed agents and prompts you to choose one.
    - Inspects the agent's `llms[*].model_name` and looks for cheaper compatible
      models in the workspace catalog.
    - Creates a Switchyard `random_routing` virtual model with an 80% strong /
      20% weak split and smoke-tests the route before wiring it to a sibling
      agent.
    - Suggests skill optimization, prompt tuning, and new-model evaluations
      where the agent qualifies.
    - Persists suggestions to the `nemo-agent-optimizer` fileset.

=== "Python SDK"

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )

    client.inference.virtual_models.create(
        name="routed-agent-model",
        workspace="default",
        models=[
            {"model": "default/<strong-model-entity>", "backend_format": "OPENAI_CHAT"},
            {"model": "default/<weak-model-entity>", "backend_format": "OPENAI_CHAT"},
        ],
        request_middleware=[{
            "name": "nemo-switchyard",
            "config_type": "random_routing",
            "config": {
                "strong": {"model": "default/<strong-model-entity>"},
                "weak": {"model": "default/<weak-model-entity>"},
                "strong_probability": 0.8,
                "enable_stats": False,
            },
        }],
    )
    ```

## Optimize Skills

Skill optimization applies when the agent depends on local skill files and has
an evaluation suite. The loop runs evaluations, analyzes failures, lets the
coding agent edit only the configured skills directory, reruns verification,
and keeps the change only when the evaluation result improves.

=== "CLI"

    ```bash
    nemo agents optimize-skills run --spec-file .agent-improver.yml
    ```

    Set `open_pr: true` in the YAML when you want the loop to prepare a
    reviewable branch.

    A sample `.agent-improver.yml` is in
    `plugins/nemo-agents/examples/agent-improver.example.yml`.

=== "Skill"

    Ask your coding agent:

    > Optimize the skills used by my agent and keep the changes that improve evaluation scores.

    The `agents-optimize` skill drives the skill-optimization loop when the
    selected agent has skills and an evaluation suite. Verify it is installed:

    ```bash
    nemo skills show agents-optimize
    ```

    What it does under the hood:

    - Confirms the agent uses skills (a `--skills-path`, a `.agent-improver.yml`,
      or skill files referenced from the config).
    - Runs `nemo agents optimize-skills` against the configured skills directory.
    - Re-runs evaluation and keeps the change only when scores improve.
    - Persists outcomes to the `nemo-agent-optimizer` fileset.

=== "Python SDK"

    ```python
    from nemo_agents_plugin.jobs.optimize_skills import OptimizeSkillsJob
    from nemo_platform_plugin.scheduler import NemoJobScheduler

    import yaml
    from pathlib import Path

    spec = yaml.safe_load(Path(".agent-improver.yml").read_text())
    NemoJobScheduler().run_local(
        OptimizeSkillsJob,
        spec,
        workspace="default",
    )
    ```

## Inspect Saved Results

Use the Files service to inspect what the optimizer saved:

```bash
nemo files list nemo-agent-optimizer

nemo files download nemo-agent-optimizer \
  --remote-path optimizer_suggestions.jsonl \
  -o optimizer_suggestions.jsonl

nemo files download nemo-agent-optimizer \
  --remote-path optimizer_snapshot.json \
  -o optimizer_snapshot.json
```

Telemetry is optional. If agents use the `nemo_files` telemetry exporter, trace
files are written to `nemo-agent-telemetry`, and the optimizer samples the
largest JSONL file:

```bash
nemo files list nemo-agent-telemetry
```

## Run Prompt and Parameter Tuning

The `nemo agents optimize run` command runs the NAT optimizer path for
parameter or prompt tuning. Use it when you already have a NAT optimization
YAML and want to run `nat optimize` through the Agents plugin.

For the ReAct example:

=== "CLI"

    ```bash
    nemo agents optimize run \
      --optimize-config plugins/nemo-agents/examples/react-agent/react-optimize.yml \
      --agent react-agent
    ```

=== "Skill"

    Ask your coding agent:

    > Run prompt tuning on my deployed agent against this optimization config.

    The `agents-optimize` skill suggests `nemo agents optimize run` when the
    agent has an optimization config and a baseline dataset. Verify it is
    installed:

    ```bash
    nemo skills show agents-optimize
    ```

    What it does under the hood:

    - Confirms the agent has a NAT optimization YAML.
    - Runs `nemo agents optimize run` (or `submit` for platform jobs).
    - Compares results against the evaluation baseline and surfaces deltas
      for review.

=== "Python SDK"

    ```python
    import os
    from pathlib import Path

    from nemo_agents_plugin.jobs.optimize_agent import OptimizeAgentJob
    from nemo_platform import NeMoPlatform
    from nemo_platform_plugin.scheduler import NemoJobScheduler

    WORKSPACE = "default"
    optimize_config = Path("plugins/nemo-agents/examples/react-agent/react-optimize.yml")

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace=WORKSPACE,
    )

    result = NemoJobScheduler().run_local(
        OptimizeAgentJob,
        {
            "optimize_config": str(optimize_config),
            "agent": "react-agent",
            "workspace": WORKSPACE,
        },
        workspace=WORKSPACE,
        sdk=client,
    )
    print(result)
    ```

When `--agent` is a platform-managed agent name, the job fetches the stored
agent config, merges it with the optimization config, injects the Inference
Gateway URL, and runs trials locally. When `--agent` is a raw HTTP endpoint,
the endpoint is treated as an opaque remote service, so local parameter sweeps
do not change the remote agent behavior.

## Troubleshooting

**No suggestions appear.** Confirm the workspace has agents, model entities, and a model catalog entry smaller than the agent's current model. New-model suggestions require a previous optimizer snapshot, so they do not appear on the first run.

**The model evaluation fails.** Confirm the judge model in the eval config is available through the workspace Inference Gateway. You can replace the eval files in `<agent-name>-eval` with your own evaluation config and dataset.

**Data safety suggestions do not appear.** Telemetry is optional. The optimizer only scans `nemo-agent-telemetry` when that fileset exists and contains JSONL trace files.

## Next steps

- [Agent overview](index.md): review how platform-managed agents are registered, deployed, invoked, evaluated, and optimized.
- [Agent evaluation](../evaluator/metrics/agent-configuration.md): configure agents as online evaluation targets and choose the right agent response mapping.
- [CLI reference](../cli/reference.md): look up complete command options and global CLI flags for scripted workflows.
