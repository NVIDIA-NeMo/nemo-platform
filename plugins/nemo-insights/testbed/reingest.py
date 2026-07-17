# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Re-ingest export bundles through the platform's real APIs (restore = additive re-ingest).

The consumption side of testbed export bundles: convert exported span docs back
to OTLP protobuf and POST them to Intake's ingest route, then re-post
annotations and evaluator results. Fixture-scoped restores are additive,
idempotent, and healing. Direct restores use ``require_empty=True`` and are
fresh-target-only: they fail once the target contains data.

Doc -> OTLP inversion (validated against the live platform, 2026-07-06 spike):

* Protocol fields are taken directly from the doc: ``trace_id``/``span_id``/
  ``parent_span_id`` are the original OTLP ids (Intake stores and serves the
  *external* ids), ``started_at``/``ended_at`` become nanosecond timestamps
  (DateTime64(6) — microseconds are exact), ``status == "error"`` becomes OTLP
  status code 2.
* ``raw_attributes`` (a JSON string in detailed docs) carries every attribute
  the catalog did NOT consume — it passes through verbatim. ``otel.scope`` is
  re-hoisted onto the protobuf scope (ingest unconditionally re-stamps
  ``otel.scope`` from the scope, so it must not ride along as an attribute).
* Catalog-consumed attributes (``model``, ``agent_name``, token counts, ...)
  are NOT in ``raw_attributes`` — they surface as typed doc columns. The
  inversion is derived mechanically from ``span_attribute_catalog`` (imported
  from the nemo-platform checkout): each doc value is re-emitted under the
  spec's highest-precedence source key, so ingest re-derives the identical
  semantic column. ``agent_version`` is the one catalog field the read API
  does not expose — it cannot be restored (invisible to doc-level diffs, which
  compare read-API output on both sides).
* Source-only keys (``session.id``, ``input.value``, ``output.value``,
  ``openinference.span.kind``) are synthesized from the doc's ``session_id``/
  ``input``/``output``/``kind`` fields.

Idempotency (spike-verified): spans dedup on re-ingest (deterministic
ClickHouse ORDER BY key + FINAL reads — identical payloads keep counts flat),
evaluator-result POSTs upsert (identity-derived id), but annotation POSTs
DUPLICATE (server-side uuid ids). The per-collection count guard in
:func:`ingest_bundle` is therefore the only protection against double-posting
annotations, and what lets an interrupted restore heal its missing
annotations/evaluator-results — its semantics are exact (see the function
docstring).

Provenance (spike-verified): annotation and evaluator-result POSTs reject
client ``created_at``/``created_by`` (422, ``extra="forbid"``) — both are
server-stamped at restore time, as are ``annotation_id``, ``ingested_at``,
and the workspace-scoped ``evaluator_result_id``. See ``NORMALIZED_FIELDS``.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlsplit

import httpx
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
from testbed import export
from testbed.ingest import ensure_workspace
from testbed.otlp_ingest import _add_attributes, export_trace_request

TEMP_ROOT = Path(__file__).resolve().parent / "tmp"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_EPOCH_ISO = "1970-01-01T00:00:00Z"
_STATUS_CODE_ERROR = 2  # opentelemetry.proto.trace.v1.Status.STATUS_CODE_ERROR
SPAN_BATCH = 100  # spans per OTLP request (ingest caps bodies at 5 MiB; tau2 spans are a few KB)

# Where the attribute catalog lives inside a nemo-platform checkout.
CATALOG_RELPATH = Path("services/intake/src/nmp/intake/spans/span_attribute_catalog.py")

# The dev platform's ClickHouse container: nemo-platform's
# services/intake/scripts/spans/run_clickhouse.sh always docker-runs it under this name.
CLICKHOUSE_CONTAINER = "nmp-intake-clickhouse"

# Fields normalized away in round-trip diffs — every one spike-proven unavoidable:
# - workspace: the whole point of re-ingest is restoring into a different (fixture/scratch) workspace.
# - ingested_at: stamped `utc_now()` by ingest for all three collections.
# - created_at / created_by: the annotation and evaluator-result POSTs reject client values
#   (pydantic extra="forbid" -> 422); the server stamps now()/auth-principal (None when auth is off).
# - annotation_id: server-generated uuid per POST.
# - evaluator_result_id: server-derived stable_id(workspace, session, span, name) — workspace-scoped,
#   so it necessarily changes when the workspace is remapped.
NORMALIZED_FIELDS = {
    "spans": ("workspace", "ingested_at"),
    "annotations": ("workspace", "ingested_at", "created_at", "created_by", "annotation_id"),
    "evaluator_results": ("workspace", "ingested_at", "created_at", "created_by", "evaluator_result_id"),
}

# Server-stamped fields to drop when turning an exported doc back into a POST body.
_POST_DROP = {
    "annotations": ("annotation_id", "workspace", "created_by", "created_at", "ingested_at"),
    "evaluator_results": ("evaluator_result_id", "workspace", "created_by", "created_at", "ingested_at"),
}

# The platform's entity-name rule (nmp.common NAME_PATTERN) — target workspaces must satisfy it.
_WS_OK = re.compile(r"^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$")

# Catalog fields that are not flat doc columns: nested under evaluation_context / usage_details.
_EVAL_CONTEXT_FIELDS = frozenset({"evaluation_id", "evaluation_sha", "evaluation_run_id", "test_case_id"})
_USAGE_DETAIL_FIELDS = {
    "prompt_cache_write_tokens": "prompt_details.cache_write",
    "prompt_audio_tokens": "prompt_details.audio",
    "completion_reasoning_tokens": "completion_details.reasoning",
    "completion_audio_tokens": "completion_details.audio",
}

STALE_AFTER_DAYS = 60  # spans TTL out of ClickHouse 90 days after start_time; warn well before

# Margin subtracted from a bundle's min_start_time when deriving the analyst's `since`:
# comfortably below the oldest span, so the read API's 30-day default lookback (injected
# whenever `since` is absent) can never hide restored spans.
SINCE_MARGIN = timedelta(days=1)


def default_platform_roots() -> list[Path]:
    """Auto-detect candidates for a nemo-platform checkout, in resolution order.

    First the containing monorepo, then the legacy workstation layout.
    """
    plugin_root = Path(__file__).resolve().parent.parent
    return [
        plugin_root.parents[1],
        Path.home() / "workstation" / "nemo-platform",
    ]


def resolve_platform_root(
    explicit: str | Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    candidates: list[Path] | None = None,
) -> Path:
    """Locate the nemo-platform checkout whose ``span_attribute_catalog`` drives re-ingest.

    Resolution order: explicit ``--platform-root`` > ``NMP_PLATFORM_ROOT`` env >
    the first :func:`default_platform_roots` candidate that actually contains the
    catalog. Explicit/env paths are taken at face value (:func:`load_catalog`
    raises the precise error if the catalog is missing there); with nothing
    found, exit with the fix.
    """
    if explicit:
        return Path(explicit)
    env = os.environ if env is None else env
    if env.get("NMP_PLATFORM_ROOT"):
        return Path(env["NMP_PLATFORM_ROOT"])
    for candidate in default_platform_roots() if candidates is None else candidates:
        if (candidate / CATALOG_RELPATH).is_file():
            return candidate
    sys.exit(
        "no nemo-platform checkout found (its span_attribute_catalog drives the re-ingest "
        "attribute inversion) — pass --platform-root PATH or set NMP_PLATFORM_ROOT"
    )


def bundle_digest(bundle: Path) -> str:
    """Fixture-workspace suffix for a local bundle file: sha256 of its bytes, first 8 hex chars."""
    return hashlib.sha256(Path(bundle).read_bytes()).hexdigest()[:8]


def fixture_workspace_map(workspaces: list[str], suffix: str) -> dict[str, str]:
    """Map bundle workspaces onto fixture-scoped restore targets: ``<ws>-<suffix>``.

    Restores never write into a source-named workspace: published refs land in
    ``<ws>-<ref>`` (e.g. ``tau2-airline-state-v6``), local bundle files in
    ``<ws>-<sha256(bundle)[:8]>``. Every target must satisfy the platform's
    entity-name rule — checked here so the CLI fails before any network I/O
    (:func:`ingest_bundle` re-checks per workspace as a backstop).
    """
    mapping = {ws: f"{ws}-{suffix}" for ws in workspaces}
    for target in mapping.values():
        if not _WS_OK.fullmatch(target):
            sys.exit(f"fixture workspace '{target}' violates the platform naming rule ({_WS_OK.pattern})")
    return mapping


def explicit_workspace_map(workspaces: list[str], into: str) -> dict[str, str]:
    if len(workspaces) != 1:
        sys.exit(
            "restore --into requires a single-workspace bundle; "
            f"found {len(workspaces)}: {', '.join(sorted(workspaces))}"
        )
    if not _WS_OK.fullmatch(into):
        sys.exit(f"workspace {into!r} violates the platform naming rule ({_WS_OK.pattern})")
    return {workspaces[0]: into}


def manifest_since(manifest: dict) -> datetime:
    """The analyst's explicit lower bound for a restored bundle: ``min_start_time`` floored.

    The intake read API injects a 30-day default lookback whenever ``since`` is
    absent — analyzing a restored bundle without an explicit bound at or below
    its oldest span silently reads nothing. Returns ``min_start_time`` minus
    :data:`SINCE_MARGIN`; epoch when the manifest has no span time bounds.
    """
    raw = manifest.get("min_start_time")
    if not raw:
        return _EPOCH
    oldest = datetime.fromisoformat(str(raw))
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    return oldest - SINCE_MARGIN


def load_catalog(platform_root: Path) -> ModuleType:
    """Import ``span_attribute_catalog`` straight from a nemo-platform checkout.

    The catalog module is pure stdlib (dataclasses/enum/decimal), so it loads
    by file path without installing the platform's packages. The module must be
    registered in ``sys.modules`` before exec: its dataclasses use
    ``from __future__ import annotations`` and field-type resolution looks the
    module up by name.
    """
    path = Path(platform_root) / CATALOG_RELPATH
    if not path.is_file():
        raise FileNotFoundError(
            f"span_attribute_catalog not found at {path} — pass the root of a nemo-platform checkout"
        )
    spec = importlib.util.spec_from_file_location("testbed_span_attribute_catalog", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _doc_value(doc: dict, field: str) -> Any:
    """The doc's value for a catalog semantic field (most are flat columns; a few are nested)."""
    if field in _EVAL_CONTEXT_FIELDS:
        return (doc.get("evaluation_context") or {}).get(field)
    if field in _USAGE_DETAIL_FIELDS:
        return (doc.get("usage_details") or {}).get(_USAGE_DETAIL_FIELDS[field])
    if field == "agent_version":
        return None  # consumed at ingest but never exposed by the read API — unrecoverable
    return doc.get(field)


def _iso_to_ns(value: str) -> int:
    """Doc timestamp (ISO, naive = UTC) -> OTLP nanoseconds, exact to the stored microsecond."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return ((dt - _EPOCH) // timedelta(microseconds=1)) * 1000


def doc_to_otlp(doc: dict, catalog) -> dict:
    """One detailed span doc -> a plain OTLP span dict (no protobuf, no network).

    Returns ``{trace_id, span_id, parent_span_id, name, start_ns, end_ns,
    status_error, scope, attributes}`` — :func:`build_trace_request` turns a
    batch of these into one protobuf request. ``catalog`` is the platform's
    ``span_attribute_catalog`` module (see :func:`load_catalog`); the semantic
    doc columns are inverted through it mechanically, so a catalog change on
    the platform side changes the inversion with it.
    """
    attrs: dict[str, Any] = json.loads(doc.get("raw_attributes") or "{}")
    # Ingest re-stamps otel.scope from the protobuf scope on every span, so the exported value
    # must travel as the scope itself (build_trace_request groups spans by it), not as an attribute.
    scope = json.loads(attrs.pop("otel.scope", "null") or "null")
    attrs["session.id"] = doc["session_id"]  # source-only keys never appear in raw_attributes
    if doc.get("input") is not None:
        attrs["input.value"] = doc["input"]
    if doc.get("output") is not None:
        attrs["output.value"] = doc["output"]
    if doc.get("status") == "cancelled":
        attrs["status"] = "cancelled"  # source-only; the only OTLP route to a cancelled row
    if "openinference.span.kind" not in attrs and doc.get("kind") not in (None, "UNKNOWN"):
        attrs["openinference.span.kind"] = doc["kind"]
    for spec in catalog.ATTRIBUTE_SPECS:
        if any(key in attrs for key in spec.source_keys):
            continue  # raw passthrough already carries a source alias — let it win, as it did originally
        value = _doc_value(doc, spec.field.value)
        if value is not None:
            attrs[spec.source_keys[0]] = value
    metadata = (doc.get("evaluation_context") or {}).get("metadata")
    if metadata and "nemo.experiment.metadata" not in attrs:
        # Stored in the string bag but excluded from raw_attributes; resurfaces as evaluation_context.metadata.
        attrs["nemo.experiment.metadata"] = json.dumps(metadata, separators=(",", ":"), ensure_ascii=False)
    if not doc.get("trace_id"):
        raise ValueError(f"span {doc.get('span_id')}: no trace_id — cannot rebuild an OTLP span")
    return {
        "trace_id": doc["trace_id"],
        "span_id": doc["span_id"],
        "parent_span_id": doc.get("parent_span_id"),
        "name": doc.get("name") or "",
        "start_ns": _iso_to_ns(doc["started_at"]),
        "end_ns": _iso_to_ns(doc["ended_at"]) if doc.get("ended_at") else 0,
        "status_error": doc.get("status") == "error",
        "scope": scope,
        "attributes": attrs,
    }


def build_trace_request(otlp_spans: list[dict]) -> ExportTraceServiceRequest:
    """Batch OTLP span dicts into one ``ExportTraceServiceRequest``.

    Spans are grouped into one ScopeSpans per distinct ``scope`` value so the
    original ``otel.scope`` round-trips. No resource attributes are set: the
    original resource layer (e.g. ``service.name``) was merged into the span
    attributes at first ingest and now rides in the raw-attributes passthrough.
    """
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    by_scope: dict[str, Any] = {}
    for spec in otlp_spans:
        scope_key = json.dumps(spec["scope"], sort_keys=True)
        scope_spans = by_scope.get(scope_key)
        if scope_spans is None:
            scope_spans = resource_spans.scope_spans.add()
            if spec["scope"]:
                scope_spans.scope.name = spec["scope"].get("name") or ""
                scope_spans.scope.version = spec["scope"].get("version") or ""
            by_scope[scope_key] = scope_spans
        span = scope_spans.spans.add()
        span.trace_id = bytes.fromhex(spec["trace_id"])
        span.span_id = bytes.fromhex(spec["span_id"])
        if spec.get("parent_span_id"):
            span.parent_span_id = bytes.fromhex(spec["parent_span_id"])
        span.name = spec["name"]
        span.start_time_unix_nano = spec["start_ns"]
        span.end_time_unix_nano = spec["end_ns"]
        if spec["status_error"]:
            span.status.code = _STATUS_CODE_ERROR
        _add_attributes(span.attributes, spec["attributes"])
    return request


def _collection_count(
    base_url: str, workspace: str, collection: str, time_field: str, *, client: httpx.Client | None = None
) -> int:
    """Total docs in one workspace collection, read off the list endpoint's pagination total.

    ``page_size=1`` — only ``pagination.total_results`` is consumed. The time
    filter carries an explicit epoch bound because the read API injects a
    30-day default lookback whenever none is given (older docs would silently
    vanish from the count).
    """
    url = f"{base_url.rstrip('/')}/apis/intake/v2/workspaces/{workspace}/{collection}"
    params = {"page": 1, "page_size": 1, f"filter[{time_field}][gte]": _EPOCH_ISO}
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.get(url, params=params)
    finally:
        if owns_client:
            client.close()
    if resp.status_code != 200:
        raise RuntimeError(f"{collection} count failed for {workspace} ({resp.status_code}): {resp.text}")
    return int(resp.json()["pagination"]["total_results"])


def span_count(base_url: str, workspace: str, *, client: httpx.Client | None = None) -> int:
    """Total spans in a workspace (``started_at`` >= epoch)."""
    return _collection_count(base_url, workspace, "spans", "started_at", client=client)


def annotation_count(base_url: str, workspace: str, *, client: httpx.Client | None = None) -> int:
    """Total annotations in a workspace (``created_at`` >= epoch)."""
    return _collection_count(base_url, workspace, "annotations", "created_at", client=client)


def evaluator_result_count(base_url: str, workspace: str, *, client: httpx.Client | None = None) -> int:
    """Total evaluator results in a workspace (``created_at`` >= epoch)."""
    return _collection_count(base_url, workspace, "evaluator-results", "created_at", client=client)


def _require_zero(workspace: str, collection: str, count: int) -> None:
    if count:
        raise RuntimeError(
            f"{workspace}: direct restore requires an empty target, but it has "
            f"{count} {collection}. Choose a fresh workspace or explicitly delete "
            "and recreate this one."
        )


def _collection_outcome(documents: list[dict], ingested: bool) -> dict[str, int]:
    count = len(documents)
    if ingested:
        return {"ingested": count, "skipped": 0}
    return {"ingested": 0, "skipped": count}


def _post_created(client: httpx.Client, url: str, body: dict) -> None:
    resp = client.post(url, json=body)
    if not (200 <= resp.status_code < 300):
        raise RuntimeError(f"POST {url} failed ({resp.status_code}): {resp.text}")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _wait_for_spans(
    base_url: str,
    workspace: str,
    expected: int,
    *,
    client: httpx.Client,
    timeout_s: float = 60.0,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Block until the workspace serves ``expected`` spans (ingest -> queryable lag).

    Transient poll failures — transport errors and non-200 count responses
    (``span_count`` raises RuntimeError on those) — are treated as
    not-yet-visible and retried until the deadline, same spirit as
    ``ingest.poll_visible``; the last one is quoted in the timeout error.
    """
    deadline = time.monotonic() + timeout_s
    count = 0
    last_error: Exception | None = None
    while True:
        try:
            count = span_count(base_url, workspace, client=client)
            last_error = None
            if count >= expected:
                return
        except (httpx.HTTPError, RuntimeError) as exc:
            last_error = exc
        if time.monotonic() >= deadline:
            detail = f" (last poll error: {last_error})" if last_error is not None else ""
            raise RuntimeError(f"{workspace}: only {count}/{expected} spans queryable after {timeout_s:.0f}s{detail}")
        sleep(1.0)


def _is_loopback(base_url: str) -> bool:
    """True when the target is the local dev platform — the docker ClickHouse is *its* backing store."""
    return urlsplit(base_url).hostname in {"localhost", "127.0.0.1", "::1"}


def _stop_local_ttl_merges(*, container: str = CLICKHOUSE_CONTAINER) -> None:
    """Best-effort ``SYSTEM STOP TTL MERGES`` on the local ClickHouse; never raises.

    Intake TTL-drops spans 90 days after ``start_time`` — restoring a stale
    bundle without freezing TTL merges silently loses the rows on the next
    merge. CI's stack does this unconditionally; this is the laptop-restore
    equivalent. On failure, prints the manual command instead.
    """
    command = ["docker", "exec", container, "clickhouse-client", "-q", "SYSTEM STOP TTL MERGES"]
    try:
        proc = subprocess.run(command, capture_output=True, text=True)
        failure = (proc.stderr.strip() or f"exit {proc.returncode}") if proc.returncode != 0 else None
    except Exception as exc:  # docker missing entirely, exec error — protection stays best-effort
        failure = str(exc)
    if failure:
        print(
            f"could not stop TTL merges ({failure}) — run this manually or restored spans may vanish:\n"
            f'  docker exec {container} clickhouse-client -q "SYSTEM STOP TTL MERGES"',
            file=sys.stderr,
        )
    else:
        print(
            f"TTL merges stopped on {container} (stale bundle: restored spans are past the 90-day TTL)", file=sys.stderr
        )


def _first_span_id(base_url: str, workspace: str, *, client: httpx.Client | None = None) -> str | None:
    """The workspace's earliest span id (``started_at`` ascending), or None when the probe can't answer.

    Fingerprint for the count-guard skip path: ``page_size=1`` + ``sort=started_at``
    with an explicit epoch bound (the read API injects a 30-day default lookback).
    Any failure — transport error, non-200, empty page — returns None: the probe
    is hardening, never a blocker.
    """
    url = f"{base_url.rstrip('/')}/apis/intake/v2/workspaces/{workspace}/spans"
    params = {"page": 1, "page_size": 1, "sort": "started_at", "filter[started_at][gte]": _EPOCH_ISO}
    owns_client = client is None
    client = client or httpx.Client(timeout=30.0)
    try:
        resp = client.get(url, params=params)
        if resp.status_code != 200:
            return None
        data = resp.json().get("data") or []
        return (data[0] or {}).get("span_id") if data else None
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if owns_client:
            client.close()


def _assert_same_first_span(base_url: str, workspace: str, span_docs: list[dict], *, client: httpx.Client) -> None:
    """Harden the count-only skip guard: matching counts can still be a different corpus.

    A re-minted ref (same workspaces, same counts, fresh ids — e.g. re-published
    via ``--clobber``) would silently pass the count guard and every later read
    would run against the WRONG corpus. Compare the live workspace's first span
    (``started_at`` asc) against the bundle's; any bundle doc tied at the minimum
    ``started_at`` qualifies. A probe failure falls back to the count-only guard
    (see :func:`_first_span_id`) — hardening must never block a restore.
    """
    live_first = _first_span_id(base_url, workspace, client=client)
    if live_first is None:
        return
    earliest = min(str(doc.get("started_at") or "") for doc in span_docs)
    expected = {doc.get("span_id") for doc in span_docs if str(doc.get("started_at") or "") == earliest}
    if live_first not in expected:
        raise RuntimeError(
            f"{workspace}: span count matches the bundle but its first span is {live_first!r} "
            f"(bundle expects one of {sorted(expected)!r}) — the workspace holds a DIFFERENT corpus "
            "with matching counts (re-minted ref?). Delete the fixture workspace and restore again."
        )


def warn_if_stale(manifest: dict, *, now: datetime | None = None) -> str | None:
    """Warn (stderr) when the bundle's spans are old enough to be at TTL risk; return the message.

    Intake's spans table TTLs rows 90 days after ``start_time`` — restoring an
    old bundle plants spans that the next TTL merge silently deletes — and the
    read API injects a 30-day default lookback when no explicit ``since`` is
    passed. Warn at ``STALE_AFTER_DAYS`` so both traps are visible early.
    """
    raw = manifest.get("min_start_time")
    if not raw:
        return None
    oldest = datetime.fromisoformat(str(raw))
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    age_days = (now - oldest).days
    if age_days <= STALE_AFTER_DAYS:
        return None
    message = (
        f"WARNING: bundle spans start {age_days} days ago (min_start_time={raw}).\n"
        "  Intake TTL-drops spans 90 days after start_time — restored rows can vanish on the next\n"
        "  TTL merge. Freeze TTL merges on the target ClickHouse first:\n"
        '    docker exec nmp-intake-clickhouse clickhouse-client --query "SYSTEM STOP TTL MERGES"\n'
        "  Reads also default to a 30-day lookback: always pass an explicit `since` at or before\n"
        f"  min_start_time ({raw}) when querying restored spans."
    )
    print(message, file=sys.stderr)
    return message


def ingest_bundle(
    base_url: str,
    export_dir: Path,
    manifest: dict,
    *,
    workspace_map: dict[str, str],
    catalog,
    require_empty: bool = False,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Re-ingest a bundle's export into the mapped workspaces through the real APIs.

    ``export_dir`` is the bundle's ``export/`` directory (one subdir per source
    workspace); ``workspace_map`` maps every manifest workspace to its target.
    Per workspace, the idempotency guard runs FIRST and is PER COLLECTION — an
    interrupted restore (transient POST failure, span-visibility timeout) can
    leave spans landed with annotations/evaluator-results missing, and a
    span-only guard would skip the workspace forever without healing it:

    * spans: live count equal to the manifest -> skip span ingest; zero -> ingest
      (OTLP batches, then wait until queryable); any other mismatch -> hard error
      (partially restored spans, or foreign data).
    * evaluator results: equal -> skip; fewer than the manifest -> post ALL of
      them (POSTs upsert on a server-derived stable id, so re-posting is safe —
      announced as healing); more -> hard error (foreign data).
    * annotations: equal -> skip; zero existing -> post; anything else -> hard
      error — annotation POSTs mint fresh server-side uuids, so re-posting a
      partial set would duplicate; there is no safe heal (delete + re-restore).

    With ``require_empty=True``, all three target collections must be empty
    before the first data write and each non-empty collection is rechecked
    immediately before its first write. This direct-restore mode is not
    idempotent into a populated workspace.

    "already restored — skipping" is printed only when EVERY collection is
    satisfied. Returns
    ``{source_ws: {"workspace": target, <collection>: {"ingested": n, "skipped": n}}}``.

    Only otel-sourced corpora are restorable: ATIF/chat-completions span docs
    carry non-hex ids (``span-<digest>``, ``chatcmpl-<hash>``) that the OTLP
    inversion cannot encode, and re-ingest would re-stamp their ``source`` as
    otel. Every workspace's docs are scanned up front so a bad bundle errors
    before ANYTHING is ingested (all-or-nothing).
    """
    spans_by_ws: dict[str, list[dict]] = {}
    foreign_sources: dict[str, Counter] = {}
    for source_ws in manifest["workspaces"]:
        docs = _read_jsonl(Path(export_dir) / source_ws / "spans.jsonl")
        spans_by_ws[source_ws] = docs
        bad = Counter(doc.get("source") for doc in docs if doc.get("source") != "otel")
        if bad:
            foreign_sources[source_ws] = bad
    if foreign_sources:
        detail = "; ".join(
            f"workspace '{ws}': "
            + ", ".join(f"{src or '<missing>'}={n}" for src, n in sorted(bad.items(), key=lambda kv: str(kv[0])))
            for ws, bad in foreign_sources.items()
        )
        raise RuntimeError(
            f"bundle contains non-otel span docs ({detail}) — their ids are not OTLP hex, so re-ingest "
            "would crash mid-batch (partial restore) and any doc that survived would be silently "
            "re-stamped as otel. Only otel-sourced corpora are restorable today; nothing was ingested."
        )
    if warn_if_stale(manifest) and _is_loopback(base_url):
        # CI's stack freezes TTL merges unconditionally; a laptop restore of a >90d bundle
        # would otherwise lose its spans on the next TTL merge with only an ignorable warning.
        _stop_local_ttl_merges()
    outcome: dict[str, dict] = {}
    counts = manifest.get("counts") or {}
    with httpx.Client(timeout=60.0) as client:
        for source_ws in manifest["workspaces"]:
            try:
                target = workspace_map[source_ws]
            except KeyError:
                raise RuntimeError(f"workspace_map has no target for bundle workspace '{source_ws}'") from None
            if not _WS_OK.fullmatch(target):
                raise RuntimeError(f"target workspace '{target}' violates the platform naming rule ({_WS_OK.pattern})")
            ws_dir = Path(export_dir) / source_ws
            spans = spans_by_ws[source_ws]
            annotations = _read_jsonl(ws_dir / "annotations.jsonl")
            results = _read_jsonl(ws_dir / "evaluator_results.jsonl")
            ws_counts = counts.get(source_ws) or {}
            expected_spans = int(ws_counts.get("spans", len(spans)))
            expected_ann = int(ws_counts.get("annotations", len(annotations)))
            expected_res = int(ws_counts.get("evaluator_results", len(results)))
            ensure_workspace(base_url, target, client=client)

            have_spans = span_count(base_url, target, client=client)
            if require_empty:
                have_ann = annotation_count(base_url, target, client=client)
                have_res = evaluator_result_count(base_url, target, client=client)
                for collection, count in (
                    ("spans", have_spans),
                    ("annotations", have_ann),
                    ("evaluator results", have_res),
                ):
                    _require_zero(target, collection, count)
                ingest_spans = bool(spans)
                post_annotations = bool(annotations)
                post_results = bool(results)
            else:
                if have_spans == expected_spans:
                    ingest_spans = False
                    if expected_spans and spans:
                        # Counts alone can't tell a restored corpus from a re-minted one — fingerprint it.
                        _assert_same_first_span(base_url, target, spans, client=client)
                elif have_spans == 0:
                    ingest_spans = True
                else:
                    raise RuntimeError(
                        f"{target}: has {have_spans} spans but the bundle expects {expected_spans} — the workspace "
                        "is partially restored (or holds foreign data). Delete the workspace (or map to a fresh "
                        "one) and restore again."
                    )
                have_ann = annotation_count(base_url, target, client=client)
                if have_ann == expected_ann:
                    post_annotations = False
                elif have_ann == 0:
                    post_annotations = True
                else:
                    raise RuntimeError(
                        f"{target}: has {have_ann} annotations but the bundle expects {expected_ann} — annotation "
                        "POSTs mint fresh server-side ids, so re-posting would duplicate what is already there "
                        "(there is no safe partial re-post). Delete the fixture workspace (or map to a fresh one) "
                        "and restore again."
                    )
                have_res = evaluator_result_count(base_url, target, client=client)
                if have_res == expected_res:
                    post_results = False
                elif have_res < expected_res:
                    post_results = True  # upsert-safe: re-post the FULL set
                else:
                    raise RuntimeError(
                        f"{target}: has {have_res} evaluator results but the bundle expects {expected_res} — the "
                        "workspace holds foreign evaluator results. Delete the fixture workspace (or map to a "
                        "fresh one) and restore again."
                    )

            if not (ingest_spans or post_annotations or post_results):
                print(f"{target}: already restored ({have_spans} spans) — skipping")
                outcome[source_ws] = {
                    "workspace": target,
                    "spans": _collection_outcome(spans, False),
                    "annotations": _collection_outcome(annotations, False),
                    "evaluator_results": _collection_outcome(results, False),
                }
                continue
            # Healing = posting into a workspace whose spans already landed (interrupted restore).
            healing = expected_spans > 0 and not ingest_spans
            if ingest_spans:
                print(f"ingesting {len(spans)} spans into {target}")
                for start in range(0, len(spans), SPAN_BATCH):
                    batch = [doc_to_otlp(doc, catalog) for doc in spans[start : start + SPAN_BATCH]]
                    request = build_trace_request(batch)
                    if require_empty and start == 0:
                        _require_zero(target, "spans", span_count(base_url, target, client=client))
                    export_trace_request(base_url, target, request, client=client)
                if spans:
                    _wait_for_spans(base_url, target, expected_spans or len(spans), client=client, sleep=sleep)
            root = f"{base_url.rstrip('/')}/apis/intake/v2/workspaces/{target}"
            if post_annotations:
                if healing:
                    print(f"{target}: healing annotations: posting {len(annotations)}")
                for index, doc in enumerate(annotations):
                    body = {k: v for k, v in doc.items() if k not in _POST_DROP["annotations"]}
                    if require_empty and index == 0:
                        _require_zero(target, "annotations", annotation_count(base_url, target, client=client))
                    _post_created(client, f"{root}/annotations", body)
            if post_results:
                if healing:
                    print(f"{target}: healing evaluator results: posting {len(results)}")
                for index, doc in enumerate(results):
                    body = {k: v for k, v in doc.items() if k not in _POST_DROP["evaluator_results"]}
                    if require_empty and index == 0:
                        _require_zero(
                            target, "evaluator results", evaluator_result_count(base_url, target, client=client)
                        )
                    _post_created(client, f"{root}/evaluator-results", body)
            outcome[source_ws] = {
                "workspace": target,
                "spans": _collection_outcome(spans, ingest_spans),
                "annotations": _collection_outcome(annotations, post_annotations),
                "evaluator_results": _collection_outcome(results, post_results),
            }
    return outcome


def _normalize(doc: dict, collection: str) -> dict:
    """Strip the spike-proven server-stamped fields; parse raw_attributes so ordering can't matter."""
    normalized = {k: v for k, v in doc.items() if k not in NORMALIZED_FIELDS[collection]}
    if collection == "spans":
        normalized["raw_attributes"] = json.loads(normalized.get("raw_attributes") or "{}")
    return normalized


def _canonical(doc: dict) -> str:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False)


def _diff_collection(original: list[dict], restored: list[dict], *, workspace: str, collection: str) -> list[str]:
    """Doc-level diff of one collection, normalized per ``NORMALIZED_FIELDS``; [] = identical."""
    left = sorted((_normalize(doc, collection) for doc in original), key=_canonical)
    right = sorted((_normalize(doc, collection) for doc in restored), key=_canonical)
    mismatches: list[str] = []
    if len(left) != len(right):
        mismatches.append(f"{workspace}/{collection}: {len(left)} exported vs {len(right)} restored")
    for doc_a, doc_b in zip(left, right):
        if doc_a == doc_b:
            continue
        label = doc_a.get("span_id") or doc_a.get("session_id") or "?"
        for key in sorted(set(doc_a) | set(doc_b)):
            if doc_a.get(key) != doc_b.get(key):
                mismatches.append(f"{workspace}/{collection} {label}.{key}: {doc_a.get(key)!r} != {doc_b.get(key)!r}")
    return mismatches


def cleanup_scratch(base_url: str, workspaces: list[str], *, container: str = CLICKHOUSE_CONTAINER) -> None:
    """Best-effort scratch-workspace cleanup after a round-trip check.

    There is NO delete API for spans/annotations/evaluator-results rows — row
    cleanup only works where the docker ClickHouse container IS the target's
    backing store, i.e. loopback targets (the local dev platform); the DELETE
    mutations are scoped to an exact IN-list of the scratch names. On remote
    targets NOTHING is deleted — docker-execing the local container would purge
    the wrong ClickHouse, and deleting just the workspace *record* would orphan
    the remote rows behind it (a later same-name restore would silently diff
    against them). Leaving the record intact means a later collision hits the
    loud foreign-data guard instead; the leftovers are printed for manual
    cleanup. Failures are reported, never raised: on CI the whole platform is
    ephemeral, so residue is moot.
    """
    if not workspaces:
        return
    if not _is_loopback(base_url):
        print(
            f"cleanup: remote target {base_url} — no row-delete API exists and the local docker "
            "ClickHouse is not this target's store. Left behind for manual cleanup (rows AND "
            f"workspace records): {', '.join(workspaces)}\n"
            "  (records kept on purpose: a later same-name restore then trips the loud "
            "foreign-data guard instead of silently diffing against orphaned rows)",
            file=sys.stderr,
        )
        return
    names = ",".join(f"'{ws}'" for ws in workspaces)
    if any("'" in ws or not _WS_OK.fullmatch(ws) for ws in workspaces):
        print(f"cleanup: refusing to build a DELETE for suspicious names: {workspaces}", file=sys.stderr)
        return
    if shutil.which("docker"):
        for table in ("spans", "annotations", "evaluator_results", "trace_index"):
            proc = subprocess.run(
                [
                    "docker",
                    "exec",
                    container,
                    "clickhouse-client",
                    "--query",
                    f"DELETE FROM intake.{table} WHERE workspace IN ({names})",
                ],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                print(f"cleanup: rows in {table} not deleted ({proc.stderr.strip()})", file=sys.stderr)
    else:
        print("cleanup: docker unavailable — scratch rows left in ClickHouse (no delete API exists)", file=sys.stderr)
    with httpx.Client(timeout=30.0) as client:
        for ws in workspaces:
            resp = client.delete(f"{base_url.rstrip('/')}/apis/entities/v2/workspaces/{ws}")
            if resp.status_code not in (200, 204, 404):
                print(f"cleanup: workspace record {ws} not deleted ({resp.status_code})", file=sys.stderr)


def _scratch_digest(manifest: dict, content_key: str | None) -> str:
    """8-char content scope for scratch names: the bundle digest when given (used verbatim when it
    is name-safe, hashed otherwise), else a hash of the manifest's counts + span time bounds."""
    if content_key:
        cleaned = re.sub(r"[^a-z0-9]", "", content_key.lower())
        if len(cleaned) >= 8:
            return cleaned[:8]
    basis = content_key or json.dumps(
        {
            "counts": manifest.get("counts") or {},
            "min_start_time": manifest.get("min_start_time"),
            "max_start_time": manifest.get("max_start_time"),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8]


def _scratch_workspace_map(manifest: dict, scratch_prefix: str, content_key: str | None) -> dict[str, str]:
    """Scratch targets scoped by bundle content: ``<scratch_prefix><digest8>-<ws>``.

    Content scoping keeps one run's residue (remote targets have no row delete —
    see :func:`cleanup_scratch`) from colliding with the NEXT roundtrip of
    *different* content: a name collision can then only mean same-content
    residue, which the ingest guard resolves as already-restored or a loud
    foreign-data error — never a silent wrong diff. Names are truncated to the
    platform's 63-char workspace rule (``_WS_OK``) when the source name is long.
    """
    digest8 = _scratch_digest(manifest, content_key)
    mapping: dict[str, str] = {}
    for ws in manifest["workspaces"]:
        name = f"{scratch_prefix}{digest8}-{ws}"
        if len(name) > 63:
            name = name[:63].rstrip("-")
        mapping[ws] = name
    return mapping


def roundtrip_diff(
    base_url: str,
    export_dir: Path,
    manifest: dict,
    *,
    scratch_prefix: str,
    catalog,
    sleep: Callable[[float], None] = time.sleep,
    content_key: str | None = None,
) -> list[str]:
    """The mint-time fidelity guard: ingest into scratch workspaces, re-export, doc-diff.

    Every bundle workspace is re-ingested into a content-scoped scratch
    workspace (``<scratch_prefix><digest8>-<workspace>`` — pass the bundle
    digest as ``content_key``; without one the digest is derived from the
    manifest's counts and time bounds), drained back through the same read API
    the export used, and compared doc-by-doc. The comparison normalizes ONLY
    the workspace rename, the server-stamped fields in ``NORMALIZED_FIELDS``,
    and doc/field ordering. Returns mismatch descriptions — empty list = the
    bundle restores with full read-API fidelity. Scratch state is cleaned up
    best-effort (see :func:`cleanup_scratch`).
    """
    if not scratch_prefix.startswith("scratch-"):
        raise ValueError("scratch_prefix must start with 'scratch-' (cleanup deletes rows under these names)")
    workspace_map = _scratch_workspace_map(manifest, scratch_prefix, content_key)
    mismatches: list[str] = []
    try:
        ingest_bundle(base_url, export_dir, manifest, workspace_map=workspace_map, catalog=catalog, sleep=sleep)
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as tmp:
            re_dir = Path(tmp)
            export.export_workspaces(base_url, list(workspace_map.values()), re_dir, since=None)
            for source_ws, scratch_ws in workspace_map.items():
                for collection in ("spans", "annotations", "evaluator_results"):
                    original = _read_jsonl(Path(export_dir) / source_ws / f"{collection}.jsonl")
                    restored = _read_jsonl(re_dir / "export" / scratch_ws / f"{collection}.jsonl")
                    mismatches.extend(_diff_collection(original, restored, workspace=source_ws, collection=collection))
    finally:
        cleanup_scratch(base_url, list(workspace_map.values()))
    return mismatches
