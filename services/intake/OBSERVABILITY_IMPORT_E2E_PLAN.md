<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Observability Imports: End-to-End Plan

## Outcome

Add a direct JSON span-ingest endpoint and small, provider-specific import scripts so customers can
copy historical traces from MLflow, LangSmith, Arize Phoenix, and Braintrust into NeMo Intake. The
import must include feedback, annotations, expectations, and evaluation scores as well as trace
data, preserve fields Intake does not understand, and be verifiable using real provider examples.

This is a client-driven import path, not a new server-side job system. Live semantic telemetry
should continue to use OTLP when the producer already emits OpenInference or OTel GenAI spans.

## Implementation notes and resolved rough edges

- ClickHouse retention remains 90 days from provider `start_time`. Direct ingest rejects the entire
  batch with `422` when any span is already outside that window and tells the operator to increase
  both span/index TTLs before importing older data. Provider timestamps remain unchanged.
- Coverage is classified at each native record's top level. A nested container is retained whole
  when any of its leaves have no exact Intake field, so all descendant leaves inherit that preserved
  disposition. This is safer and more reviewable than provider-specific recursive deletion.
- Native feedback/evaluation records are retained whole under `<provider>.signals` even when useful
  values are also projected into typed evaluator-result or annotation APIs. That intentional
  duplication makes the import reversible and preserves event IDs, actors, timestamps, and audit
  details.
- LangSmith feedback and Phoenix annotations are separate provider resources. Offline scripts accept
  `--feedback-input` and `--annotations-input` instead of requiring customers to hand-merge files.
- Golden fixtures use explicit expected fields and typed raw JSON paths rather than copying the
  complete normalized batch a second time. Field-disposition coverage plus ClickHouse round-trip
  assertions protects the rest without an unreviewable duplicate fixture.

## Decisions

| Concern | Decision |
|---|---|
| Endpoint | `POST /apis/intake/v2/workspaces/{workspace}/ingest/spans` |
| Request shape | One JSON object containing `source` and a non-empty `spans` array |
| Response | Empty `201 Created`, matching the existing ATIF ingest convention |
| Persistence | Map into the existing `IntakeSpan`, `TraceBatch`, and `ingest_batch` path |
| Retry behavior | Existing span identity makes re-imports upsert rather than append duplicate spans |
| Provider logic | Keep it out of Intake; implement it in scripts bundled with the existing `nemo-intake` skill |
| Scores and feedback | Use the existing evaluator-results and annotations endpoints after spans are written |
| Unknown data | Preserve it as namespaced, native JSON in detailed span `raw_attributes` |
| Tests | Runtime behavior belongs in pytest; `tests.json` remains limited to skill-routing tests |

## 1. Direct span-ingest API

Add `services/intake/src/nmp/intake/spans/ingest/spans.py` and register its router in
`IntakeService.get_routers()` under the existing `Ingest` tag.

The public request should be direct and provider-neutral:

```json
{
  "source": "langsmith",
  "spans": [
    {
      "span_id": "run-2",
      "trace_id": "trace-1",
      "session_id": "thread-1",
      "parent_span_id": "run-1",
      "name": "ChatOpenAI",
      "kind": "LLM",
      "status": "success",
      "started_at": "2026-01-01T00:00:00Z",
      "ended_at": "2026-01-01T00:00:01Z",
      "input": {"messages": [{"role": "user", "content": "Hello"}]},
      "output": {"content": "Hi"},
      "attributes": {
        "gen_ai.request.model": "example-model",
        "langsmith.raw": {
          "extra": {"runtime": {"library": "langchain"}},
          "events": [{"name": "new_token", "time": "2026-01-01T00:00:00.5Z"}],
          "tags": ["production"]
        }
      }
    }
  ]
}
```

Use strict Pydantic schemas with `extra="forbid"`. Reuse `SpanKind`, `SpanStatus`,
`SpanSemanticAttributes`, `SpanAttributeBags`, `TraceBatch`, `json_dumps_preserve`, and
`SpansService.ingest_batch`; do not add a parallel domain model or storage path.

Endpoint behavior:

- Accept arbitrary non-empty string IDs rather than imposing OTLP hex-ID rules.
- Default a missing `session_id` to `trace_id`.
- Permit a parent outside the request so paged imports and partial exports remain usable.
- Reject duplicate `(trace_id, span_id)` identities within one request, self-parenting, and
  `ended_at < started_at` before writing anything.
- Reject a complete batch before writing when any `started_at` is outside the 90-day ClickHouse TTL.
- Canonically JSON-serialize structured `input` and `output` through the existing storage helper.
- Normalize recognized semantic attribute keys through the existing attribute catalog.
- Validate the whole request before calling `ingest_batch` once.

### Raw attribute preservation

Every source field must have exactly one disposition:

```text
source data fields = mapped fields + preserved raw fields + explicitly ignored transport fields
```

The endpoint accepts `attributes` as arbitrary JSON. Recognized semantic keys become existing typed
and queryable fields. All unconsumed values are stored in one internal direct-ingest raw envelope
and merged back into detailed `raw_attributes` on reads.

This envelope is necessary because `SpanAttributeBags.put_json` currently stores a dictionary or
list as a JSON-encoded string. Follow the existing `atif.raw` read/write pattern instead so nested
objects, arrays, nulls, booleans, numbers, strings, and Unicode survive the round trip as their
original JSON types. The internal envelope key must not appear in the public `raw_attributes`
object. Summary and preview reads continue to omit raw attributes under the existing behavior.

Provider adapters put their leftovers below `<provider>.raw`. Scalar top-level fields already mapped
to span fields or semantic attributes are removed; nested containers used for partial projection are
retained whole. No source data field is silently discarded. Pagination cursors, response counts,
and API links are transport metadata and may be explicitly ignored with a reason in the adapter.

## 2. Provider import scripts

Extend the existing `nemo-intake` skill instead of creating four overlapping skills:

```text
packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-intake/
  SKILL.md
  tests.json
  scripts/
    _import_common.py
    import_mlflow.py
    import_langsmith.py
    import_phoenix.py
    import_braintrust.py
  references/
    import-mlflow.md
    import-langsmith.md
    import-phoenix.md
    import-braintrust.md
```

Keep `SKILL.md` short. It should select one provider reference and script only after the user's
provider is known. Verify that the existing skill installer and vendoring package include the
companion files; do not add another installer.

The common helper owns only behavior shared by all four scripts:

- Intake URL/workspace/auth handling and the skill's HTTPS-or-loopback URL validation.
- JSON requests, pagination helpers, span batching, and error reporting.
- Stable serialization, dry-run output, and exact-content annotation deduplication.
- Posting spans first, then evaluator results, then annotations.
- Querying imported span IDs back from Intake and failing if expected records are missing.

Each script supports a bounded import (`project`, `since`, `until`), `--workspace`, `--nmp-base-url`,
`--include-feedback`, `--input` for an offline export/fixture, and `--dry-run`. Credentials come only
from provider-specific environment variables and are never written to fixtures or output.

### Provider mapping

| Provider | Trace source | Feedback/evaluation source | Intake projection |
|---|---|---|---|
| MLflow | `search_traces(..., return_type="list")` and `Trace.data.spans` | `Trace.info.assessments`, including feedback and expectations | Automated numeric/boolean assessment to evaluator result; human rating to label or feedback annotation; rationale to evaluator comment or note; expectation/correction to metadata annotation |
| LangSmith | Runs from `list_runs` or the documented runs query, preserving parent/trace IDs | Raw feedback records, not aggregated `feedback_stats` | Automated scores to evaluator results; human numeric/categorical feedback to labels; thumbs-up/down to feedback; comments to notes; correction/structured value to metadata |
| Phoenix | Project spans from the documented OTLP-JSON REST response | Span annotations endpoint | `annotator_kind` code/LLM scores to evaluator results; human score/label to label annotation; explanation to comment/note; annotation metadata to metadata |
| Braintrust | Project-log fetch events with cursor pagination | Inline scores, expected values, comments, classifications, and audit data | Scores to evaluator results; comments to notes; expected/correction values to metadata; classifications to labels when representable |

When provider provenance distinguishes human from automated output, preserve that distinction. When
it does not, use the provider's documented meaning and retain the original event under
`<provider>.raw` so the projection is reversible and auditable.

For every feedback/evaluation event, preserve source-only details that Intake's typed APIs cannot
represent—such as provider event ID, original timestamp, actor metadata, audit record, or structured
rationale—in the target span's namespaced raw data. Then create the useful typed projection through
the existing API.

Evaluator result IDs are already deterministic per workspace/session/span/name, so replay updates
the existing result. Annotation IDs are server-generated; before posting an annotation, list the
target span's existing annotations and compare the complete normalized annotation body. Reuse an
exact match and post only missing annotations.

## 3. Real provider examples

Check provider payloads into normal test fixtures:

```text
packages/nemo_platform_ext/tests/skills/fixtures/observability/
  sources.json
  mlflow-trace.json
  langsmith-runs.json
  langsmith-feedback.json
  phoenix-spans.json
  phoenix-annotations.json
  braintrust-project-log.json
```

`sources.json` records, for every fixture:

- Official documentation URL.
- Retrieval date.
- SDK/API version when the example is versioned.
- Exact transformations made locally, limited to secret redaction, deterministic replacement IDs,
  and conversion of documentation pseudocode into valid JSON.

Use official payload examples verbatim when the documentation provides complete JSON. When the
documentation provides executable code but not a complete serialized response, run the official
example against a pinned provider SDK or local server and save the actual exported object. Do not
invent an approximate payload. CI uses the pinned fixtures rather than calling provider SaaS APIs.

Fixture sources:

- [MLflow trace search](https://mlflow.org/docs/latest/genai/tracing/search-traces/) and
  [serialized trace data](https://mlflow.org/docs/latest/api_reference/_modules/mlflow/entities/trace_data.html)
- [LangSmith run data](https://docs.langchain.com/langsmith/run-data-format),
  [trace example](https://docs.langchain.com/langsmith/messages-view-trace-format), and
  [feedback data](https://docs.langchain.com/langsmith/feedback-data-format)
- [Phoenix span REST response](https://arize.com/docs/phoenix/sdk-api-reference/rest-api/api-reference/spans/search-spans-with-simple-filters-no-dsl)
  and [annotation example](https://arize.com/docs/phoenix/tracing/how-to-tracing/feedback-and-annotations/capture-feedback)
- [Braintrust underlying span](https://www.braintrust.dev/docs/instrument/advanced-tracing) and
  [project-log fetch response](https://www.braintrust.dev/docs/api-reference/logs/fetch-project-logs-get-form)

## 4. Tests

### Endpoint tests

Add focused unit tests for request validation, semantic normalization, JSON input/output
serialization, and raw-envelope reconstruction. Add
`services/intake/tests/integration/spans/test_direct_span_ingest.py` using the existing TestClient and
ClickHouse fixture to verify:

- A multi-span parent/child batch is written and read back with the correct hierarchy.
- Arbitrary source IDs and the `session_id` fallback work.
- Known semantic attributes populate typed read fields.
- Unknown scalar and nested values round-trip through `json.loads(raw_attributes)` with exact JSON
  types, including null and Unicode.
- Invalid time ranges, self-parenting, duplicate identities, and extra schema fields return `422`
  without partial writes.
- Re-posting a batch updates the same span identities without increasing the logical span count.

### Adapter tests

Add `packages/nemo_platform_ext/tests/skills/test_intake_import_scripts.py`. Parameterize it across
the checked-in provider fixtures and test the adapter functions directly. For every fixture assert:

1. Every source top-level field is classified as mapped, preserved, or explicitly ignored; all
   leaves in a preserved nested container inherit its classification.
2. The three classifications are exhaustive and disjoint.
3. Core IDs, hierarchy, timestamps, status, input, and output map to the expected direct-span body.
4. Unmapped data equals the expected `<provider>.raw` object, including native JSON types.
5. Feedback, expectations, annotations, comments, and scores produce the expected evaluator-result
   and annotation requests.

Keep expected normalized outputs as explicit golden JSON beside the inputs. This makes provider
mapping changes reviewable and prevents a new source field from disappearing unnoticed.

### Full import E2E

Add `services/intake/tests/integration/spans/test_observability_import_e2e.py`. For each official
fixture, run the real adapter over `--input` data, write its span batch through the Intake TestClient,
post its evaluator results and annotations, and query all three resources back from ClickHouse.
Assert the complete expected hierarchy, typed semantic fields, raw field preservation, evaluator
values/comments, and annotation kinds/values. Run each fixture twice and assert span/evaluator
upserts plus annotation deduplication. Mapper tests retain the official timestamps; the ClickHouse
write test rebases only normalized `started_at`/`ended_at` values into the retention window while
preserving durations and the complete native timestamps under provider raw data.

`nemo-intake/tests.json` receives only routing cases such as "import my LangSmith traces into
Intake." It does not test adapter behavior.

## 5. Delivery sequence

1. Add the endpoint schema, mapping, router registration, raw envelope, and unit/integration tests.
2. Refresh OpenAPI and update generated SDK/CLI artifacts using the existing generation workflow.
3. Add the shared import helper and one provider adapter at a time, beginning with its official
   fixtures and golden mapping tests.
4. Add feedback/evaluation retrieval and typed projection for that provider before moving to the
   next provider.
5. Add the four-provider ClickHouse E2E test and replay assertions.
6. Update the Intake README and `nemo-intake` skill/reference files.
7. Touch `tmp/restart.txt`, then smoke one checked-in fixture through a running Intake service and
   query the spans, evaluator results, and annotations back.

## 6. Validation commands

Run targeted checks while implementing, followed by the full relevant suites:

```bash
uv run --frozen pytest services/intake/tests/test_spans_schemas.py -q
uv run --frozen pytest services/intake/tests/integration/spans/test_direct_span_ingest.py -q
uv run --frozen pytest services/intake/tests/integration/spans/test_observability_import_e2e.py -q
uv run --frozen pytest packages/nemo_platform_ext/tests/skills/test_intake_import_scripts.py -q
uv run --frozen pytest sdk/python/nemo-platform/tests/test_direct_span_ingest.py -q
uv run scripts/skill-test.py --root .
uv run ruff check services/intake packages/nemo_platform_ext
uv run ruff format --check services/intake packages/nemo_platform_ext
uv run --frozen ty check
make refresh-openapi
```

Run `make update-sdk` when the Stainless credentials required by the repository workflow are
available.

## Implementation verification

Verified on 2026-08-14:

- The focused endpoint, attribute-catalog, migration, adapter, and four-provider ClickHouse suites
  pass: 90 tests, including provider pagination/error regressions and replay write-count checks.
- Ruff formatting/lint, targeted `ty`, and the pre-commit `ty` hook pass.
- The repository OpenAPI generator passes and all three checked-in platform specifications contain
  the direct-ingest operation. Static auth maps it to the existing `intake.ingest.create`
  permission. The Python SDK exposes `client.intake.ingest.spans.create`, the generated CLI exposes
  `nemo intake ingest spans create`, and a focused SDK transport test verifies the emitted JSON.
  `make refresh-openapi` could not use its Flox wrapper on this host, so the documented
  `script/generate-openapi-spec.sh` fallback was run through `uv` instead.
- A process-level MLflow fixture import through the SDK-backed writer returned two spans, one
  evaluator result, and one annotation; all were queried back. A 2020 span returned the documented
  actionable `422`, and the service plus managed ClickHouse stopped cleanly afterward.
- The full pre-commit gate's code checks pass; this host cannot run its `helm-docs` and tool-version
  hooks because `helm-docs` and `yq` are not installed. The skill-routing suite retains unrelated
  pre-existing failures while all four new import cases pass.

### Rough edges

- Stainless cloud generation requires `STAINLESS_API_KEY`, which is not available on this host.
  The checked-in SDK resource/types, Stainless mappings, generation snapshots, CLI, and focused
  transport test are synchronized locally; `make update-sdk` should still be run in a credentialed
  environment to confirm the cloud generator produces no delta.
- Retention validation rejects the whole direct-span batch when any `started_at` is outside the
  configured 90-day ClickHouse window. This prevents apparently successful imports whose old rows
  are immediately removed, but customers importing deeper history must increase both the `spans`
  and `trace_index` TTLs first.
- Provider APIs can add fields or event variants. Importers preserve unmodeled JSON under
  `<provider>.raw`/`<provider>.signals`; the checked-in official snapshots make mapping drift
  reviewable, but they do not replace periodic fixture refreshes against current provider docs.
- Direct span IDs, session IDs, parent IDs, trace IDs, and names are capped at 1024 characters to
  keep a 1000-span request bounded. Provider records beyond that limit fail validation and must be
  normalized explicitly rather than being silently truncated.
- Braintrust and Phoenix live pagination fails after 1000 pages or a repeated cursor; Braintrust
  also stops on an empty page. This makes provider API stalls visible instead of hanging an import,
  but imports above the cap must be split into smaller time windows.

## Definition of done

- The direct endpoint is in the generated OpenAPI surface and follows existing Intake auth,
  routing, error, storage, and response conventions.
- All four scripts perform bounded live imports and offline fixture imports without a server-side
  job resource.
- Trace data, provider evaluations, and human feedback are all imported.
- Every provider data field in every official fixture is mapped, preserved, or explicitly ignored.
- Nested unknown data survives a write/read round trip without stringification or type loss.
- The checked-in official examples pass mapper tests and real Intake/ClickHouse E2E tests.
- Re-running an import does not create logical duplicate spans, evaluator results, or annotations.
- The installed `nemo-intake` skill contains its scripts and references and selects them lazily.
