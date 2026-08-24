<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Intake trace source

Use this source when the trace reference starts with `intake://`.

## Requirements

- Python 3.9 or later, and no third-party packages. The bare `python3` works,
  including the 3.9 that macOS ships.
- An explicit NeMo Platform workspace
- `NMP_BASE_URL` set to the Platform origin
- `NMP_ACCESS_TOKEN` set when the Platform requires authentication

Remote Platform origins must use HTTPS. Loopback origins can use HTTP.

Every command prints one JSON object and writes no files. An exit code of `1`
means that the object contains `error` and `hint` fields. Add `--compact` to any
verb to print the JSON on one line.

In each command, replace `SKILL_DIR` with the installed
`eval-author-inspect-trace` directory, `WORKSPACE` with the NeMo Platform
workspace that holds the trace, and `TRACE_ID` with the Intake trace ID.

## List candidate traces

When neither the user nor the preceding workflow named a trace:

```bash
python3 "SKILL_DIR/scripts/inspect_trace.py" list \
  --source intake \
  --workspace "WORKSPACE" \
  --limit 20
```

Add `--agent AGENT_NAME` to keep only traces that contain a span from one agent,
and `--since ISO_TIMESTAMP` to bound the window. Each row carries a `trace_ref`
that the read verbs accept without edits, alongside `status`, `span_count`,
`error_count`, and `duration_ms`, so you can choose a trace deliberately.

An empty result carries a `note` and is not an error. Report it and stop rather
than widening the search on your own.

## Read the trace structure

```bash
python3 "SKILL_DIR/scripts/inspect_trace.py" overview \
  --trace "intake://traces/TRACE_ID" \
  --workspace "WORKSPACE"
```

This reads every span in Intake's compact form, which measured 82 times smaller
than the detailed form. A 605-span trace returns about 154 KB rather than 26 MB,
so the first read is affordable whatever the trace size. The output carries
`source`, `report_path`, `overview`, and `timeline`, and no span payloads.

## Read the spans that matter

```bash
python3 "SKILL_DIR/scripts/inspect_trace.py" spans \
  --trace "intake://traces/TRACE_ID" \
  --workspace "WORKSPACE" \
  --status error
```

Select the spans with any combination of these:

| Flag | Selects |
|---|---|
| `--status` | Spans with one status, such as `error` |
| `--kind` | Spans of one kind, such as `LLM`, `TOOL`, `CHAIN`, or `AGENT` |
| `--parent` | The direct children of one span |
| `--span-id` | One span, repeatable to name several |
| `--limit` | At most N spans when you name none, 20 by default |

`--status`, `--kind`, and `--parent` narrow the query on the server. `--span-id`
is applied after the fetch, because Intake supports no equality operator on a
span `id`. Reading stops as soon as every named span is found, so pairing
`--span-id` with `--kind` or `--status` makes the read cheaper on a long trace.

Each of `input`, `output`, and `raw_attributes` is shortened to `--max-chars`
characters, 2000 by default. A shortened field sets `FIELD_truncated` and records
the whole length in `FIELD_length`. Pass `--full` to shorten nothing, and expect
megabytes when you do. The result repeats `max_chars` at the top level, where
`null` means the payloads are whole.

## Filters Intake accepts

The span endpoint accepts `agent_name`, `kind`, `model`, `name`,
`parent_span_id`, `project`, `provider`, `session_id`, `source`, `started_at`,
`status`, `tool_name`, and `trace_id`. It rejects both `$eq` and `$in` on `id`,
so no query selects spans by span ID. The trace endpoint does accept
`id` with `$in`, which is how a batch of trace summaries is fetched.

A rejected filter returns HTTP 400 with the valid field names in `detail`.

## Adapter details

The Intake adapter makes read-only `GET` requests under
`/apis/intake/v2/workspaces/WORKSPACE`. It rejects redirects and sends
credentials only to the validated Platform origin.

The adapter lives under `scripts/sources/intake/`:

- `scripts/sources/intake/adapter.py` owns the Intake flags for all three verbs
  and returns the normalized source identity beside the result.
- `scripts/sources/intake/_http.py` validates the Platform origin,
  authenticates, encodes filters, and drains pages.
- `scripts/sources/intake/traces.py` builds Intake span and trace queries, and
  owns the one canonical `intake://traces/ID` reference form.
- `scripts/sources/intake/reader.py` reads structure compactly, joins evaluator
  results through the sessions the spans belong to, and fetches detailed
  payloads only for a named selection.
