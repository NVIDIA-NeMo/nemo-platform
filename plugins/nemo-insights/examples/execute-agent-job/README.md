<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Insights Analyst as ExecuteAgentJob Demo

This directory contains additive demo scaffolding for running the Insights
Analyst through the generic `agents.execute` job while the existing `AnalyzeJob`
continues to run side-by-side.

## Pieces

- `demo_spans.json`: a scenario spec for the target agent's telemetry, stored
  with relative time offsets so it never ages out of Intake's retention window.
- `seed_intake.py`: expands the spec into spans and annotations, posts them to
  Intake, then reads them back.
- `submit_analysis_run.py`: submits the run through the Insights analysis-runs
  API and optionally waits for the job's `analysis-report` result.

The high-level Insights service route lives in
`nemo_insights_plugin.analysis_runs.router`. It accepts an Insights-shaped
request and creates the backing `agents.execute` job with the
`insights.analysis` execute extension attached.

There is no Analyst Agent entity to provision. The Analyst's config is derived
per request — its models are chosen by the caller and its harness settings are
scoped to one run — so `nemo_insights_plugin.analyst.agent_config` builds it and
the route submits it as an inline agent definition. Nothing to seed, nothing to
keep in sync with a shipped version.

## Prerequisites

- A running local platform with Intake, Agents, Jobs, and Insights, and a
  running ClickHouse for Intake (see `services/intake/README.md`).
- `nemo setup` completed, so a default/fast Model Entity pair exists. The
  Analyst resolves its models as Platform Model Entities, so the refs must be
  workspace-qualified entity names — not raw provider model ids.

  A Model Entity existing locally does **not** mean its upstream provider still
  serves it; auto-discovered catalogs go stale, and a dead entry surfaces as a
  gateway `502` wrapping `Backend returned 404: Model not found`. Probe a
  candidate before relying on it:

  ```bash
  ENT=nvidia-nemotron-3-nano-30b-a3b
  SERVED=$(curl -s "$NMP_BASE_URL/apis/models/v2/workspaces/default/providers/nvidia-build" \
    | python3 -c "import json,sys;print(next(m['served_model_name'] for m in json.load(sys.stdin)['served_models'] if m['model_entity_id']=='default/$ENT'))")
  curl -s -X POST "$NMP_BASE_URL/apis/inference-gateway/v2/workspaces/default/model/$ENT/-/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d "{\"model\":\"$SERVED\",\"messages\":[{\"role\":\"user\",\"content\":\"say ok\"}],\"max_tokens\":5}"
  ```

  A pair verified working against `integrate.api.nvidia.com` on 2026-08-26:

  ```bash
  --default-model default/nvidia-nemotron-3-super-120b-a12b \
  --fast-model    default/nvidia-nemotron-3-nano-30b-a3b
  ```
- The `nemo-insights` package installed, so Fabric discovers the analyst
  adapter under `<sys.prefix>/share/nemo-fabric/adapters/`.

  That descriptor is *copied* into the venv at install time, not symlinked, and
  a plain `uv sync` will not refresh it for an unchanged editable package. After
  editing `insights-analyst.fabric-adapter.json`, run:

  ```bash
  uv sync --reinstall-package nemo-insights-plugin
  ```

```bash
export NMP_BASE_URL=http://localhost:8080
```

The target agent (`demo-agent` below) does not need to exist as an Agent
entity — the Analyst only matches it against each span's normalized
`agent_name`.

## Demo Flow

1. Seed Intake with telemetry for the target agent:

   ```bash
   uv run plugins/nemo-insights/examples/execute-agent-job/seed_intake.py \
     --base-url http://localhost:8080 \
     --workspace default \
     --target-agent demo-agent
   ```

   This posts to `POST .../ingest/spans` and `POST .../annotations`, then reads
   both back.

   **The corpus is sized against the Analyst's own bar, not for brevity.** The
   Analyst files an Insight only for patterns it can evidence with at least
   three representative traces, and it ranks issues recurring across many
   sessions above one-offs — so a handful of sessions reliably produces "no
   high-impact failure patterns detected". The spec expands to 84 spans across
   28 sessions spanning ~3.6 hours:

   | Scenario | Sessions | Failure |
   |---|---|---|
   | `retrieval` | 8 | `knowledge_search` returns zero documents; the agent answers anyway |
   | `handoff` | 6 | `delegate_task` fires without the conversation summary |
   | `billing` | 5 | `billing_lookup` times out at 30s |
   | `healthy` | 9 | none — grounded, cited answers |

   Plus 12 negative and 6 positive `feedback` annotations and 18 numeric
   `helpfulness` labels. Feedback matters: the Analyst's method says to start
   there, because it is the strongest signal of a real problem. Annotations are
   attached at session level, which is both the realistic shape for an end-user
   thumbs-down and the id the Analyst correlates back to spans with.

   Re-running is safe for spans — Intake keys a logical span on
   `(workspace, source, trace_id, span_id)`, so a repeat post updates in place.
   Annotations have no natural key, so pass `--skip-annotations` on a reseed to
   avoid piling up duplicates. Intake has no public delete API, so sessions
   seeded by an earlier version of the spec linger; use a fresh `--workspace` if
   you need a clean corpus.

2. Submit the execute job and wait for its report:

   ```bash
   uv run plugins/nemo-insights/examples/execute-agent-job/submit_analysis_run.py \
     --base-url http://localhost:8080 \
     --workspace default \
     --target-agent demo-agent \
     --default-model default/nvidia-nemotron-3-super-120b-a12b \
     --fast-model default/nvidia-nemotron-3-nano-30b-a3b \
     --wait
   ```

   The model pair is **required**. It lives only in the operator's local CLI
   config (`~/.config/nmp/config.yaml`), which the Platform process cannot read,
   so the request has to carry it.

3. Inspect the created Job's saved results directly if you did not use
   `--wait`. The durable comparison point is the `analysis-report` result saved
   by the Insights execute extension:

   ```bash
   curl "$NMP_BASE_URL/apis/agents/v2/workspaces/default/jobs/execute/<job-name>/results"
   curl "$NMP_BASE_URL/apis/agents/v2/workspaces/default/jobs/execute/<job-name>/results/analysis-report/download"
   ```

   The Insights the run persisted show up under
   `GET /apis/insights/v2/workspaces/default/insights?agent=demo-agent`.

## Notes

- The existing `AnalyzeJob` remains untouched for comparison. It is submitted at
  `/apis/insights/v2/workspaces/{workspace}/jobs/analyze-job`.
- The Analyst Agent entity is assumed to exist by the high-level route; the
  setup script is the demo-friendly way to create it.
- Dynamic read settings such as `since` and `evaluation_id` are request fields
  that reach the Analyst's harness settings, not execute-extension config.
- The analysis-runs route creates the backing job through the request-scoped
  platform SDK (`sdk.agents.jobs.execute.create`), so the caller's auth headers,
  base URL, and retry policy are applied. That SDK surface was added alongside
  this demo: a `NemoJob` subclass gets CLI and HTTP routes for free but no SDK
  method, so `agents.execute` had none.
