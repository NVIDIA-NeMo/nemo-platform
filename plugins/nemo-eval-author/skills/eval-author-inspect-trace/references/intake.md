<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Intake trace source

Use this source when the trace reference starts with `intake://`.

## Requirements

- Python 3.12 or later
- An explicit NeMo Platform workspace
- `NMP_BASE_URL` set to the Platform origin
- `NMP_ACCESS_TOKEN` set when the Platform requires authentication

Remote Platform origins must use HTTPS. Loopback origins can use HTTP.

## Read the trace

Run:

```bash
python3 "SKILL_DIR/scripts/inspect_trace.py" \
  --trace "intake://traces/TRACE_ID" \
  --workspace "WORKSPACE"
```

Replace the following:

- `SKILL_DIR`: the installed `eval-author-inspect-trace` skill directory
- `TRACE_ID`: the Intake trace ID
- `WORKSPACE`: the NeMo Platform workspace that contains the trace

The Intake adapter makes read-only `GET` requests under
`/apis/intake/v2/workspaces/WORKSPACE`. It rejects redirects and sends
credentials only to the validated Platform origin.

The adapter lives under `scripts/sources/intake/`:

- `scripts/sources/intake/adapter.py` validates source arguments and returns the
  normalized source identity and trace evidence.
- `scripts/sources/intake/_http.py` validates the Platform origin,
  authenticates, encodes filters, and drains pages.
- `scripts/sources/intake/traces.py` builds Intake span and trace queries. Trace
  inspection reaches only the trace-summary query. The span and agent-corpus
  queries wait on the audit flow that consumes them.
- `scripts/sources/intake/reader.py` loads detailed spans and related evaluator
  results.

The command prints one JSON object and writes no files. An exit code of `1`
means that the object contains `error` and `hint` fields.
