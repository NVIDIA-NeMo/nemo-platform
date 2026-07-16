<!--
Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Insights Testbed PR 66 Port Design

## Goal

Port every durable, NeMo-OO-independent testbed behavior from
NVIDIA-dev/NeMo-Optimizer PR 66 into `plugins/nemo-insights` without regressing
the profile, restore, fixture-access, credential, or publishing behavior merged
by Platform PR 718.

The work starts from Platform `origin/main` at
`2412ab7b84e98c77ecf01aa15d26da83c99e321d`. The source behavior is taken from
Optimizer PR 66 at its refreshed head
`46dc74942d9f3f69481dbac2c3e21c9770bcee5e`.

## Boundaries

The Platform Insights plugin owns the Analyst and its generic testbed. The port
therefore includes generic intake and benchmark restore, analysis, snapshot,
baseline, and registry behavior.

The port does not include the Harbor producer adapter, the vendored NeMo-OO
wheel, NeMo-OO runtime code, or Experimentalist code. `nemo-oo-airline` remains
an intake subject that replays the already-published `state-v9` fixture.
Published `state-v8`, `state-v9`, and `state-v10` assets remain unchanged on the
`NVIDIA-dev/NeMo-Optimizer` `testbed-state` release.

## Analysis and Baseline Transaction

`testbed analyze <subject>` checks a successful analysis into
`testbed/insights/<subject>.yaml` by default. `--no-check-in` leaves the runtime
output under `testbed/tmp/` and does not change checked-in files or provenance.

`testbed analyze all` selects every registry subject whose type is `benchmark`
or `intake`, sorts the names, and requires a state pin for every selected
subject before starting analysis. It rejects options that conflict with pinned
multi-subject operation.

Each child analysis runs with `--no-check-in`. If any child fails or any
expected runtime YAML is absent, checked-in YAML and manifest files remain
unchanged. After every child succeeds, the parent stages the complete desired
baseline set, then atomically replaces the checked-in files as one directory
transaction. The committed set contains exactly one subject YAML per
analyzable registry subject plus `manifest.yaml`; stale subject YAMLs are
removed. A top-level `analyze all --no-check-in` performs all analyses but skips
the promotion transaction.

All generated baseline content comes from the merged Platform Analyst. No
Optimizer Insight body is copied or hand-edited.

## Provenance

`testbed/insights/manifest.yaml` maps each analyzable subject to:

- `state`: the exact pin from `state.lock`
- `insights_sha256`: SHA-256 of the complete checked-in subject YAML bytes
- `analyst_sha256`: one deterministic fingerprint for the Platform Analyst

The Analyst fingerprint hashes sorted relative paths and bytes of Python files
under `plugins/nemo-insights/src/nemo_insights_plugin/analyst`, followed by the
canonical serialized `uv.lock` package entries that resolve the Analyst's
direct behavior-affecting dependencies. The dependency allowlist is derived
from the Platform `nemo-insights-plugin` package and excludes NeMo-OO. It does
not copy the Optimizer fingerprint or hash.

A repository test recomputes the fingerprint, subject file hashes, expected
file set, and state pins. This makes stale or manually copied provenance fail
verification.

## Restore Correctness

Restored OTLP export requests are built incrementally and bounded by both:

- at most 100 spans
- at most 4 MiB according to protobuf `ByteSize()`

A single span whose request exceeds 4 MiB fails before any request is posted.
Existing collection guards, deduplication, fixture workspace remapping, and
`restore --into` fresh-workspace validation remain unchanged.

Tau2 policy discovery checks `policy.md` and then `main_policy.md` in both
supported Tau2 directory layouts. This supports Telecom without changing
Airline or Retail behavior.

The registry removes NVQ and adds `glamr`, `nemo-oo-airline`, `tau2-retail`,
and `tau2-telecom`. State pins are `state-v8`, `state-v9`, and `state-v10` as
already published, while the existing Airline pin is preserved.

## GLAMR Authentication

GLAMR support remains testbed-only. A dedicated client builds an
`httpx.AsyncClient` with Basic authentication and rewrites the SDK Intake
prefix to GLAMR's configured Intake prefix before passing it to
`AsyncNeMoPlatform`.

Registry configuration stores only environment variable names, never
credentials. Live analysis and snapshot export preserve the remote
authentication fields and inject the custom client. Pinned analysis restores
the fixture locally and strips all remote authentication and path-rewrite
fields when retargeting the subject to the local Platform.

The generic Analyst runner accepts an injected Platform client so callers own
authentication policy. Product CLI and job callers continue to construct the
normal Platform client, preserving profile-driven commands and existing
authenticated/unauthenticated Platform behavior.

## PR 718 Compatibility

The port extends the merged implementation rather than replacing it:

- profile discovery, environment loading, preflight, and output selection are
  unchanged
- `restore --into` keeps single-workspace, empty-target, and validation-order
  guarantees
- release operations continue to use the explicit `TESTBED_STATE_REPO`
  boundary and protected read credentials
- fixture publishing remains immutable, manually guarded, and absent from
  automatic CI publishing
- no credential value enters registry files, generated artifacts, logs, or
  provenance

## Verification

Development follows focused red-green tests for each behavior. Final
verification runs:

```text
uv run --group insights pytest plugins/nemo-insights/tests/ -q
uv run ruff check plugins/nemo-insights/
uv run ruff format --check plugins/nemo-insights/
uv run --frozen ty check plugins/nemo-insights/src/nemo_insights_plugin/
```

Additional checks recompute every manifest hash, resolve `state-v8`,
`state-v9`, and `state-v10` through the configured cross-repository release,
and inspect dependency metadata to confirm no NeMo-OO dependency was added.

Baseline regeneration runs `analyze all` against a suitable local Platform
Intake stack with the merged Analyst and required inference/release
credentials. If that environment is unavailable, orchestration and validation
remain fully tested, generated YAML is not invented, and regeneration is
reported as a concrete blocker.
