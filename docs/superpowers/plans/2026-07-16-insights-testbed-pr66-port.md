<!--
Copyright (c) 2026, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
SPDX-License-Identifier: Apache-2.0
-->

# Insights Testbed PR 66 Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the durable, NeMo-OO-independent behavior from Optimizer PR 66 into the Platform Insights testbed.

**Architecture:** Extend the merged Platform testbed through its existing adapter, restore, release, and CLI seams. Keep GLAMR authentication in testbed-only code, make Analyst client ownership explicit, and stage all baseline outputs before a single promotion phase.

**Tech Stack:** Python 3.11+, argparse, asyncio, httpx, NeMo Platform SDK, protobuf OTLP, PyYAML, pytest, Ruff, ty, uv.

## Global Constraints

- Start from Platform `origin/main` commit `2412ab7b84e98c77ecf01aa15d26da83c99e321d`.
- Source behavior comes from refreshed Optimizer PR 66 head `46dc74942d9f3f69481dbac2c3e21c9770bcee5e`.
- Do not modify NeMo-Optimizer.
- Do not add the Harbor producer, Experimentalist, vendored NeMo-OO wheel, or any NeMo-OO dependency.
- Preserve profile-driven Insights commands, `restore --into`, explicit `TESTBED_STATE_REPO` access, credential boundaries, immutable publishing, and the absence of automatic fixture publishing.
- Do not copy or hand-edit Optimizer-generated Insight bodies or Optimizer Analyst provenance.
- Use `uv` exclusively and include SPDX headers on every new file.
- Every production behavior starts with a failing focused test.

---

### Task 1: Explicit Analyst Client Ownership and GLAMR Intake Client

**Files:**
- Create: `plugins/nemo-insights/testbed/intake_client.py`
- Create: `plugins/nemo-insights/tests/testbed/test_intake_client.py`
- Create: `plugins/nemo-insights/tests/test_analyst_run.py`
- Modify: `plugins/nemo-insights/src/nemo_insights_plugin/analyst/run.py`
- Modify: `plugins/nemo-insights/src/nemo_insights_plugin/cli.py`
- Modify: `plugins/nemo-insights/src/nemo_insights_plugin/jobs/analyze.py`
- Modify: `plugins/nemo-insights/testbed/adapters.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_adapters.py`
- Modify: `plugins/nemo-insights/tests/test_cli_profile.py`
- Modify: `plugins/nemo-insights/tests/test_periodic_analysis.py`

**Interfaces:**
- Produces: `build_rewriting_http_client(...) -> httpx.AsyncClient`
- Produces: `build_basic_auth_intake_client(...) -> AsyncNeMoPlatform`
- Changes: `run_analyst(..., client: AsyncNeMoPlatform) -> str`; ownership transfers to `run_analyst`, which always closes it.
- Consumes: existing `nemo_insights_plugin.client.make_client(base_url)` for normal Platform callers.

- [ ] **Step 1: Add failing GLAMR client tests**

Test path rewriting, query preservation, Basic authorization, non-Intake paths, and SDK client construction:

```python
async def test_rewrites_sdk_prefix_and_attaches_basic_auth():
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": []})

    client = build_rewriting_http_client(
        username="intake",
        password="secret",
        transport=httpx.MockTransport(handler),
    )
    try:
        response = await client.get(
            "https://agenthub.aire.nvidia.com/apis/intake/v2/workspaces/default/spans?page=1"
        )
    finally:
        await client.aclose()

    assert response.status_code == 200
    assert seen["url"] == "https://agenthub.aire.nvidia.com/api/intake/v2/workspaces/default/spans?page=1"
```

- [ ] **Step 2: Verify the client tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_intake_client.py -q
```

Expected: collection fails because `testbed.intake_client` does not exist.

- [ ] **Step 3: Implement the testbed-only Basic-auth client**

Implement constants for `/apis/intake/` and `/api/intake/`, an async request hook that rewrites `request.url.raw_path`, and builders that pass `httpx.BasicAuth`, a 60-second timeout, and the custom client to `AsyncNeMoPlatform`.

- [ ] **Step 4: Verify the GLAMR client tests pass**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Add failing Analyst ownership tests**

Cover use of the exact injected client, closure after success, and closure if `make_analyst_backend` raises:

```python
async def test_client_closed_when_backend_construction_raises(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(run_module, "make_analyst_backend", raising_backend)

    with pytest.raises(RuntimeError, match="backend failed"):
        await run_module.run_analyst(
            agent="agent",
            agent_spec=None,
            workspace="workspace",
            base_url="https://platform",
            client=client,
        )

    assert client.closed
```

- [ ] **Step 6: Verify the ownership tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/test_analyst_run.py -q
```

Expected: `run_analyst` rejects `client=`.

- [ ] **Step 7: Inject clients at every Analyst call site**

Make `client` required in `run_analyst`, move backend construction inside its `try`, and remove internal client construction. Product CLI and job paths call `make_client(base_url)`; BenchmarkAdapter does the same. IntakeAdapter chooses the GLAMR client only when `auth == "basic"` and validates both env-var names and values in `check()`.

- [ ] **Step 8: Verify Analyst, adapter, profile, and job tests**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/test_analyst_run.py \
  plugins/nemo-insights/tests/testbed/test_adapters.py \
  plugins/nemo-insights/tests/test_cli_profile.py \
  plugins/nemo-insights/tests/test_periodic_analysis.py -q
```

Expected: all pass, including existing profile-driven behavior.

- [ ] **Step 9: Commit Task 1**

```text
git add plugins/nemo-insights
git commit -s -m "feat(insights): support basic-auth Intake analysis"
```

---

### Task 2: Preserve GLAMR Snapshot Auth and Strip It on Local Restore

**Files:**
- Create: `plugins/nemo-insights/tests/testbed/test_artifact_snapshot_auth.py`
- Modify: `plugins/nemo-insights/testbed/artifact.py`
- Modify: `plugins/nemo-insights/testbed/export.py`
- Modify: `plugins/nemo-insights/testbed/cli.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_export.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_cli.py`

**Interfaces:**
- Produces: `artifact._basic_auth_intake_client_for(subjects, source_url) -> AsyncNeMoPlatform | None`
- Changes: `export_workspaces(..., client: AsyncNeMoPlatform | None = None) -> dict`
- Changes: `_with_base(subject, base, *, drop_auth: bool = True) -> Subject`
- Consumes: Task 1 `build_basic_auth_intake_client`.

- [ ] **Step 1: Add failing snapshot-auth tests**

Test client construction from named env vars, missing-credential errors, non-basic subjects, propagation into `export_workspaces`, and closure of injected clients.

- [ ] **Step 2: Verify snapshot-auth tests fail**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/testbed/test_artifact_snapshot_auth.py \
  plugins/nemo-insights/tests/testbed/test_export.py -q
```

Expected: missing helper and unsupported `client=` failures.

- [ ] **Step 3: Implement snapshot client injection**

`_basic_auth_intake_client_for` reads only credential values named by the registry, normalizes the Intake prefix to a trailing slash, and exits with a subject-specific message when a credential is absent. `snapshot_export` passes the resulting client into `export_workspaces`; `_export_workspaces` owns and closes whichever client it uses.

- [ ] **Step 4: Add failing retarget-auth tests**

Assert that:

```python
assert _with_base(glamr, "http://localhost:8080").config == {
    "agent": "glamr",
    "workspace": "default",
    "base_url": "http://localhost:8080",
}
assert _with_base(glamr, "https://remote", drop_auth=False).config["auth"] == "basic"
```

- [ ] **Step 5: Verify retarget-auth tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_cli.py -q -k with_base
```

Expected: `_with_base` does not accept `drop_auth` and retains remote auth keys.

- [ ] **Step 6: Implement mode-specific auth handling**

Define `_REMOTE_AUTH_KEYS = ("auth", "intake_path_prefix", "auth_user_env", "auth_password_env")`. Pinned/state analysis uses the default `drop_auth=True`; snapshot and `--live` pass `drop_auth=False`.

- [ ] **Step 7: Verify Task 2 tests**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/testbed/test_artifact_snapshot_auth.py \
  plugins/nemo-insights/tests/testbed/test_export.py \
  plugins/nemo-insights/tests/testbed/test_cli.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit Task 2**

```text
git add plugins/nemo-insights
git commit -s -m "fix(insights): preserve Intake auth across snapshots"
```

---

### Task 3: Bound Restore Requests and Discover Telecom Policy

**Files:**
- Modify: `plugins/nemo-insights/testbed/reingest.py`
- Modify: `plugins/nemo-insights/testbed/tau2run.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_reingest.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_tau2run.py`

**Interfaces:**
- Produces: `build_trace_requests(docs, catalog) -> list[ExportTraceServiceRequest]`
- Constants: `OTLP_REQUEST_MAX_BYTES = 4 * 1024 * 1024`, `OTLP_REQUEST_MAX_SPANS = 100`
- Changes: `read_policy` checks `policy.md` then `main_policy.md` under each supported domain root.

- [ ] **Step 1: Add failing byte-limit and oversized-span tests**

Monkeypatch small byte limits to prove a request splits before posting and that one oversized span raises before the first call to `export_trace_request`.

- [ ] **Step 2: Verify restore tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_reingest.py -q \
  -k "serialized_size or oversized_span"
```

Expected: count-only batching violates the requested assertions.

- [ ] **Step 3: Implement dual-limit request construction**

Convert each document once, calculate the candidate protobuf `ByteSize()`, flush the previous batch at 100 spans or above 4 MiB, and reject a one-span body above 4 MiB. Replace the fixed slice loop in `ingest_bundle` while preserving the `require_empty` recheck before the first post.

- [ ] **Step 4: Add and verify a failing Telecom policy test**

Create nested and flat fixtures with `main_policy.md`; run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_tau2run.py -q
```

Expected before implementation: Telecom policy returns `None`.

- [ ] **Step 5: Implement policy filename fallback**

For each domain root, test `policy.md` and then `main_policy.md`, returning the first existing UTF-8 file.

- [ ] **Step 6: Verify Task 3 tests**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/testbed/test_reingest.py \
  plugins/nemo-insights/tests/testbed/test_tau2run.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit Task 3**

```text
git add plugins/nemo-insights
git commit -s -m "fix(insights): bound restored OTLP requests"
```

---

### Task 4: Registry, State Pins, Transactional Analyze-All, and Provenance

**Files:**
- Modify: `plugins/nemo-insights/testbed/testbeds.toml`
- Modify: `plugins/nemo-insights/testbed/state.lock`
- Modify: `plugins/nemo-insights/testbed/cli.py`
- Modify: `plugins/nemo-insights/testbed/README.md`
- Create: `plugins/nemo-insights/tests/testbed/test_checked_in_insights.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_cli.py`
- Modify: `plugins/nemo-insights/tests/testbed/test_registry.py`

**Interfaces:**
- Produces: `_check_in_insights`, `_analyst_sha256`, `_write_insights_manifest`, `_remove_stale_insights`, `_analyze_all`
- Adds: `analyze all`, `analyze --no-check-in`
- Registry analyzable set: `glamr`, `nemo-oo-airline`, `tau2-airline`, `tau2-retail`, `tau2-telecom`
- State pins: `state-v8`, `state-v9`, existing Airline pin, and `state-v10` for Retail/Telecom.

- [ ] **Step 1: Add failing registry tests**

Assert NVQ is absent, GLAMR carries only env-var names, `nemo-oo-airline` is an intake subject, Telecom uses `small`, and every analyzable subject has the expected state pin.

- [ ] **Step 2: Verify registry tests fail**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/testbed/test_registry.py \
  plugins/nemo-insights/tests/testbed/test_checked_in_insights.py -q
```

Expected: new subject and baseline assertions fail.

- [ ] **Step 3: Update registry and state pins**

Port only the GLAMR, intake replay, Retail, and Telecom stanzas. Delete NVQ. Do not add the Harbor stanza or any producer dependency.

- [ ] **Step 4: Add failing single-subject check-in tests**

Cover default check-in with SPDX, manifest merge, source-output absence, and `--no-check-in` leaving checked-in files untouched.

- [ ] **Step 5: Verify single-subject tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_cli.py -q \
  -k "checks_in_insights or no_check_in or analyst_hash"
```

Expected: CLI has no check-in/provenance behavior.

- [ ] **Step 6: Implement Platform provenance**

Set the Analyst root to `plugins/nemo-insights/src/nemo_insights_plugin/analyst`. Hash sorted source paths and bytes plus canonical `uv.lock` entries for the Platform Analyst's resolved behavior-affecting direct dependencies. The allowlist must not contain NeMo-OO. Hash checked-in YAML bytes after adding SPDX.

- [ ] **Step 7: Add failing analyze-all transaction tests**

Cover:

- every benchmark/intake subject runs in sorted order with child `--no-check-in`
- all pins are validated before subprocess execution
- a child failure leaves all checked-in files unchanged
- missing child output leaves all checked-in files unchanged
- top-level `--no-check-in` skips promotion
- successful promotion replaces all expected YAMLs and removes stale YAMLs
- incompatible flags fail before execution

- [ ] **Step 8: Verify analyze-all tests fail**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_cli.py -q -k analyze_all
```

Expected: `all` is treated as an unknown subject.

- [ ] **Step 9: Implement staged analyze-all promotion**

Run each child through `sys.executable -m testbed analyze <name> --no-check-in`. After all outputs exist, build the complete checked-in set in a temporary sibling directory, including SPDX and a manifest computed from staged bytes. Swap the staged directory into place with backup-and-rollback handling so exceptions before commit preserve the old set and stale YAMLs disappear only on successful promotion.

- [ ] **Step 10: Document the workflow**

Document default check-in, exploratory `--no-check-in`, all-subject semantics, manifest fields, GLAMR credential names, and cross-repository state ownership. Keep manual guarded publishing instructions from PR 718.

- [ ] **Step 11: Verify Task 4 tests**

Run:

```text
uv run --group insights pytest \
  plugins/nemo-insights/tests/testbed/test_cli.py \
  plugins/nemo-insights/tests/testbed/test_registry.py \
  plugins/nemo-insights/tests/testbed/test_checked_in_insights.py -q
```

Expected: orchestration tests pass. The checked-in baseline test may remain blocked until Task 5 produces valid Platform-generated YAML.

- [ ] **Step 12: Commit Task 4**

```text
git add plugins/nemo-insights
git commit -s -m "feat(insights): add reproducible all-subject baselines"
```

---

### Task 5: Regenerate Baselines and Verify the Port

**Files:**
- Generate: `plugins/nemo-insights/testbed/insights/glamr.yaml`
- Generate: `plugins/nemo-insights/testbed/insights/nemo-oo-airline.yaml`
- Generate: `plugins/nemo-insights/testbed/insights/tau2-airline.yaml`
- Generate: `plugins/nemo-insights/testbed/insights/tau2-retail.yaml`
- Generate: `plugins/nemo-insights/testbed/insights/tau2-telecom.yaml`
- Generate: `plugins/nemo-insights/testbed/insights/manifest.yaml`

**Interfaces:**
- Consumes: the Task 4 `analyze all` workflow.
- Produces: only merged Platform Analyst output and current Platform provenance.

- [ ] **Step 1: Verify release asset resolution**

Run read-only release checks through the Platform implementation with `TESTBED_STATE_REPO=NVIDIA-dev/NeMo-Optimizer`. Resolve/download `state-v8`, `state-v9`, and `state-v10` into the testbed cache and verify each resulting file exists and is non-empty.

- [ ] **Step 2: Check baseline-generation prerequisites**

Verify, without printing values:

- `INFERENCE_API_KEY` is present
- `gh` has release-read access
- ClickHouse 24.3-compatible storage is available
- a local Platform Intake stack can become ready on the selected URL

If one is unavailable, record the exact missing prerequisite and do not create baseline YAML or stale provenance.

- [ ] **Step 3: Run all-subject generation when prerequisites are available**

From `plugins/nemo-insights`:

```text
uv run python -m testbed analyze all \
  --base http://localhost:8080 \
  --platform-root ../..
```

Expected: five successful analyses followed by one checked-in promotion.

- [ ] **Step 4: Validate baseline hashes**

Run:

```text
uv run --group insights pytest plugins/nemo-insights/tests/testbed/test_checked_in_insights.py -q
```

Expected when generated: manifest keys, state pins, source fingerprint, and every subject hash pass.

- [ ] **Step 5: Run the required verification suite**

```text
uv run --group insights pytest plugins/nemo-insights/tests/ -q
uv run ruff check plugins/nemo-insights/
uv run ruff format --check plugins/nemo-insights/
uv run --frozen ty check plugins/nemo-insights/src/nemo_insights_plugin/
```

- [ ] **Step 6: Confirm no NeMo-OO dependency**

Search `plugins/nemo-insights/pyproject.toml`, root dependency groups, new testbed code, and the lock fingerprint allowlist. The only allowed textual `nemo-oo` occurrence is the intake subject name and its generated baseline content.

- [ ] **Step 7: Review the completed diff**

Run a code review focused on PR 718 regressions, credential leakage, direct restore validation order, atomic promotion failure paths, and generated provenance.

- [ ] **Step 8: Commit final generated/verification changes**

If baselines were generated:

```text
git add plugins/nemo-insights/testbed/insights
git commit -s -m "test(insights): check in Platform Analyst baselines"
```

If generation was blocked, commit only implementation/test adjustments and leave `testbed/insights` absent rather than fabricating files.

- [ ] **Step 9: Report the final commit**

Return the final local Platform `HEAD` SHA as the exact commit for the future Optimizer cleanup pin, together with changed files, ported behavior, verification results, baseline status, and blockers. Do not push or merge.
