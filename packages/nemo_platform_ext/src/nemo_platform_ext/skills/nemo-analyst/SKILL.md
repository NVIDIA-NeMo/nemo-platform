---
name: nemo-analyst
description: >-
  Analyze an agent's production traces to find recurring failure patterns and
  record each as an Insight. Surveys spans, evaluator scores, and user feedback
  across many sessions, clusters similar failures, then files every finding as a
  titled Insight carrying the trace IDs that evidence the problem. Answers why
  an agent keeps failing, where it gets things wrong, and the recurring
  problems hiding in production traces. Produces the Insight that
  nemo-experimentalist consumes.
triggers:
  - nemo-analyst
  - analyze my agent's traces
  - why my agent keeps failing
  - generate insights for my agent
  - find recurring failure patterns
  - run the analyst
  - my agent keeps getting wrong
not-for:
  - nemo-experimentalist (use to act on an Insight and change the agent; this skill produces the Insight it consumes)
  - nemo-intake (use to instrument an agent, ingest telemetry, or query raw spans; this skill interprets telemetry that already landed)
  - nemo-experiments-upload (use to upload traces and evaluation results into Intake; this skill reads them back out)
  - nemo-explore (use to design an agent that does not exist yet; this skill needs a running agent with traces)
  - nemo-evaluator (use to author evaluations and metrics; this skill analyzes production behavior)
compatibility: >-
  nemo-platform >= 0.1.0; requires the Insights plugin, a reachable platform
  with Intake telemetry for the target agent, and INFERENCE_API_KEY for NVIDIA
  Inference Gateway access. No Docker or datasets needed.
maturity: beta
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read]
---

# NeMo Analyst

Find what an agent keeps getting wrong, from its own telemetry, and record it as
an Insight.

## What it produces

An Insight is a persistent, named description of one recurring problem, and it
is the unit of work the rest of the optimization loop runs on. Each carries:

- `title` — a sentence naming the failure, such as "Retrieval drops relevant
  context near the token limit"
- `description` — the failure mode, the tool or model call it affects, and the
  conditions that trigger it
- `trace_refs` — the Intake trace IDs cited as evidence, so a developer can
  audit the reasoning and build regression tests

The Analyst targets at least three representative traces per Insight and appends
evidence to an existing Insight rather than filing a near-duplicate. Two
well-evidenced Insights are worth more than ten vague ones, so a run that files
nothing is a valid outcome.

## Before running

The Analyst reads telemetry; it cannot create it. Confirm all three:

- The target agent already has traces in Intake. No traces means no Insights.
- `INFERENCE_API_KEY` is set. The Analyst runs on Claude Opus 4.8 through the
  NVIDIA Inference Gateway and reads **only** this variable. It does not use the
  `NEMO_EXPERIMENTALIST_MODELS_*` tiers the Experimentalist needs, so do not
  copy that configuration here.
- The platform is reachable at `NMP_BASE_URL`.

An `AGENT-SPEC.md` is optional but makes the Analyst materially better: given
the agent's intended behavior it can flag divergence from that contract, not
just outright errors.

## Pre-flight

```bash
nemo agents analyst doctor
```

Two failures block a run and must be fixed first: an `optimizer.yaml` that is
missing or unparseable when no `--agent` is passed, and an unset
`INFERENCE_API_KEY`. Platform reachability and the workspace probe are advisory
— they warn, and the run still proceeds.

## Run it

```bash
nemo agents analyst run \
  --agent <agent-name> \
  --workspace <workspace> \
  --base-url "$NMP_BASE_URL"
```

Add `--agent-spec AGENT-SPEC.md` to enable divergence checking, and `--verbose`
to stream the Analyst's tool calls and reasoning to stderr while it works.
Expect a run to take several minutes; it surveys many sessions before drilling
into any of them.

From an agent directory, an `optimizer.yaml` profile supplies `agent`,
`workspace`, and `agent_spec`, so the flags above become optional:

```bash
nemo agents analyst run
```

The profile is discovered by walking up from the current directory. Only those
three fields are read from it; other keys belong to the Experimentalist and are
ignored.

## Where Insights are stored

Insights always go to the platform. To keep a local copy, pass
`--insights-file-output`, which mirrors what the platform stored, platform IDs
included, and merges into that file on each run:

```bash
nemo agents analyst run --agent <agent-name> --insights-file-output .nemo-optimizer/insights.yaml
```

That path is the one the Experimentalist reads by default, so it is the
conventional choice when handing off locally. A mirror that cannot be written
degrades to a warning rather than failing the run, because the platform is the
source of truth.

## Verify

Do not report success without checking that Insights actually landed. There is
no CLI verb for this yet, so read the Insights API directly:

```bash
curl --fail-with-body \
  -H "Authorization: Bearer $(nemo auth token)" \
  "$NMP_BASE_URL/apis/insights/v2/workspaces/<workspace>/insights?agent=<agent-name>&page=1&page_size=20"
```

Drop the `Authorization` header on a local platform with authentication
disabled. A successful run leaves at least one Insight for the agent, each with
a clear title, an actionable description, and non-empty `trace_refs`. Stored
Insights also appear in Studio under the workspace's optimizer view. If you
passed `--insights-file-output`, read the mirror back and confirm it is
non-empty.

## When it finds nothing

An empty result is either a real "nothing worth filing" or one of two setup
problems. Check the agent name matches the `agent_name` on the spans exactly,
since the Analyst scopes everything through spans, then confirm telemetry is
actually flowing for that agent and workspace. Too few traces produces the same
empty result as a healthy agent.

## Hand off

Once an Insight exists, the Experimentalist acts on it:

```bash
nemo agents experimentalist run
```

For the full data model, the Analyst's tool set, periodic analysis via
`nemo insights analysis enable`, and the rest of the loop, see
[Insight-Driven Optimization](https://github.com/NVIDIA-NeMo/nemo-platform/blob/main/docs/agents/insight-driven-optimization.mdx).
