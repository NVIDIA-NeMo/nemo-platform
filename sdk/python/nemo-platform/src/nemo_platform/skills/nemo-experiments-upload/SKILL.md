---
name: nemo-experiments-upload
description: End-to-end guide for getting evaluation data into NeMo Platform Intake so it shows up as Experiments. Create an Experiment Group, create an Evaluation, then log traces and evaluator results via the ATIF (Harbor), chat-completions, or OTLP ingest endpoint — and view the rollups in Studio. Use when a user wants to upload, log, ingest, publish, or send evaluation runs, agent traces, or scores to NeMo Experiments / Intake.
triggers:
  - log traces to intake
  - upload experiment results
  - ingest evaluation data
  - how do I log to experiments
  - send traces to nemo intake
  - publish evaluation results
  - log to experiments
  - upload harbor / atif results
  - get my eval data into nemo
not-for:
  - nemo-evaluator (use to AUTHOR and RUN evaluations/metrics; this skill UPLOADS results)
  - nemo-status (use for a read-only platform health dashboard)
  - nemo-skill-selection (use for dispatch when intent is unclear)
compatibility: nemo-platform >= 0.1.0; needs the intake service running (auth, entities, intake) and ClickHouse for rollups/results; talks HTTP to /apis/intake/v2 (curl only, no Docker); Experiments viewing in Studio is behind the VITE_FF_EXPERIMENT feature flag.
maturity: beta
license: Apache-2.0
user-invocable: true
allowed-tools: [Bash, Read, Write]
---

# Log evaluation data to NeMo Intake

Get evaluation runs into the platform end-to-end: **create an Experiment Group → create an Evaluation → log traces + scores to an ingest endpoint → see the rollups.** The API says "Evaluation" and "Experiment Group"; the whole feature is called **Experiments**.

Everything below uses `${NMP_BASE_URL}` (default `http://localhost:8080`) and a `${WORKSPACE}` (default `default`). All routes are under `/apis/intake/v2/workspaces/${WORKSPACE}`.

## Pre-flight

Confirm intake is up before doing anything. If this fails, the platform isn't running — route to `setup`/`nemo-status` and stop.

```bash
set -euo pipefail
: "${NMP_BASE_URL:=http://localhost:8080}"
: "${WORKSPACE:=default}"
if curl -sf "${NMP_BASE_URL}/health/ready" >/dev/null; then
  echo "platform ready"
else
  echo "NOT READY — platform isn't running; route to setup/nemo-status and stop" >&2
  exit 1
fi
```

## What you do

Run the steps in order. Steps 1–2 create the entities; step 3 logs the data; steps 4–5 verify.

### 1. Create an Experiment Group

A group is the leaderboard container. You need its `id` for the next step.

```bash
set -euo pipefail
: "${NMP_BASE_URL:=http://localhost:8080}"
: "${WORKSPACE:=default}"
groups="${NMP_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/experiment-groups"
# Create the group. 201 = created, 409 = already exists; any other status is a real failure.
code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${groups}" \
  -H 'Content-Type: application/json' \
  -d '{"name": "my-experiment-group", "description": "example run"}')
case "${code}" in
  201|409) ;;
  *) echo "group create failed: HTTP ${code}" >&2; exit 1 ;;
esac
# Fetch the id (works whether it was just created or already existed).
GROUP_ID=$(curl -sf "${groups}/my-experiment-group" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
[ -n "${GROUP_ID}" ] || { echo "could not resolve experiment group id" >&2; exit 1; }
echo "group id: ${GROUP_ID}"
```

The POST accepts only `201` (created) or `409` (already exists) — any other status stops the step
instead of masking it. The `id` is then read with a GET, so this works on both first run and re-run;
`set -euo pipefail` + the `[ -n ]` guard keep it from continuing with an empty `GROUP_ID`.

### 2. Create an Evaluation

One Evaluation = one agent/config run against a dataset (one leaderboard row). Its **`name`** is what you reference later in `evaluation_context.evaluation_id`.

```bash
curl -sf -X POST \
  "${NMP_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations" \
  -H 'Content-Type: application/json' \
  -d "{\"name\": \"my-eval-baseline\",
       \"experiment_group_id\": \"${GROUP_ID}\",
       \"dataset_name\": \"my-dataset\",
       \"dataset_version\": \"v1\",
       \"metadata\": {\"model\": \"provider/model\", \"job_name\": \"baseline\"}}"
```

- `experiment_group_id` is the group's **`id`** (from step 1).
- `metadata` values must be **strings** (`dict[str, str]`).
- **You must create the Evaluation before you can log to it** — ingesting with an unknown `evaluation_id` returns `400 "…must be created before it can be logged."`

### 3. Log traces + evaluator results

Pick the ingest endpoint that matches your producer. **Read `references/ingest-formats.md` for the full schema and a copy-pasteable example for each.** How you attach evaluation identity depends on the endpoint:

- **ATIF and chat-completions** (JSON body) — add an `evaluation_context = {evaluation_id: "<the Evaluation name>", test_case_id: "<task id>"}` object to the payload.
- **OTLP** — there is no body field; set identity as **root-span resource attributes** `nemo.experiment.id` (the Evaluation **name**) and `nemo.test_case.id`. Spans missing these still ingest but won't associate to an Evaluation.

| Producer | Endpoint | Read |
|---|---|---|
| **Harbor / agent trajectories** (most common) | `POST .../ingest/atif` | `references/harbor-quickstart.md` |
| A single captured model call | `POST .../ingest/chat-completions` | `references/ingest-formats.md` |
| OpenTelemetry spans | `POST .../ingest/otlp/v1/traces` | `references/ingest-formats.md` |

Evaluator **scores** arrive one of two ways (both covered in the references):
- **Automatically** with ATIF — put rewards under `extra.verifier_result.rewards` (one key per criterion).
- **Explicitly** — `POST .../evaluator-results` with `{span_id, session_id, name, data_type, value}` — use `string_value` instead of `value` for `CATEGORICAL`/`TEXT` results (see `references/ingest-formats.md`).

### 4. Verify the data landed

```bash
curl -sf "${NMP_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/my-eval-baseline" \
  | python3 -m json.tool
```

Then list the ingested sessions:

```bash
curl -sf "${NMP_BASE_URL}/apis/intake/v2/workspaces/${WORKSPACE}/evaluations/my-eval-baseline/sessions" \
  | python3 -m json.tool
```

### 5. View in Studio

Open Studio → the **Experiments** area (behind the `VITE_FF_EXPERIMENT` flag) → your group → your evaluation. You'll see the leaderboard row with score/cost/latency rollups and can drill into individual sessions and traces.

## Reference files

Read these before hand-writing a payload:

- **`references/ingest-formats.md`** — the three ingest endpoints in full: request schemas, how `evaluation_context` and evaluator results attach, and a working example for each (ATIF, chat-completions, OTLP).
- **`references/harbor-quickstart.md`** — the Harbor path specifically: mapping a Harbor trial result → an ATIF payload, including verifier rewards → evaluator scores.
- **`references/troubleshooting.md`** — every common `400`/`422`/`503` from the ingest and CRUD endpoints, with the fix.

## Verification

You succeeded when `GET .../evaluations/my-eval-baseline` shows:
- `run_count` ≥ 1 (each ingested session counts as one run), and
- non-empty `evaluator_names` / `aggregate_scores` if you logged rewards, and/or `cost_usd` if your spans carried cost.

If `run_count` is 0 after ingesting, the traces didn't associate — almost always a wrong evaluation identity: `evaluation_context.evaluation_id` for ATIF/chat-completions, or the `nemo.experiment.id` root-span attribute for OTLP (see Gotchas).

## If verification fails

| Symptom | Cause | Recovery |
|---|---|---|
| `400 "…must be created before it can be logged."` | Ingested before the Evaluation existed, or `evaluation_id` doesn't match | Create the Evaluation (step 2); ensure `evaluation_context.evaluation_id` equals its **name** |
| `422 Unprocessable` on ingest | Unknown/typo'd top-level key (ATIF/chat-completions are `extra="forbid"`) or bad `schema_version` | Check the exact schema in `references/ingest-formats.md`; remove stray keys |
| Ingest 2xx but `run_count` stays 0 | Evaluation identity missing/wrong — `evaluation_context.evaluation_id` (ATIF/chat-completions) or the `nemo.experiment.id` root-span attribute (OTLP) ≠ the Evaluation's name | Attach the identity for your endpoint; use the Evaluation **name**, not its id |
| `503` on GET evaluation / sessions | ClickHouse (telemetry store) not running | Start ClickHouse; rollups and sessions require it |
| Scores don't show up | Rewards not under `extra.verifier_result.rewards`, or wrong `data_type` on `/evaluator-results` | See `references/troubleshooting.md` |

## Gotchas

- **Create before you log.** The Evaluation entity must exist before any ingest referencing it — otherwise `400`.
- **`evaluation_id` is the Evaluation's `name`, not its entity id.** But **`experiment_group_id` is the group's `id`.** Different identifiers; easy to swap.
- **OTLP uses the attribute key `nemo.experiment.id`** (and `nemo.test_case.id`) — the span-attribute key still says "experiment" even though the JSON body field is `evaluation_context`. Set `nemo.experiment.id` on your root span.
- **Use `/evaluations`, not `/experiments`.** `/experiments` still works as a deprecated hidden alias but you should log to `/evaluations`.
- **`metadata` is `dict[str, str]`** — stringify non-string values or you'll get a `422`.
- **ATIF and chat-completions are `extra="forbid"`** (unknown keys → 422); `evaluation_context` itself is lenient (`extra="ignore"`).
