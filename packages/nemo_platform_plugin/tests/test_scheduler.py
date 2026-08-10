# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`nemo_platform_plugin.scheduler`.

The public scheduler surface submits jobs remotely and explains job schemas.
These tests pin URL/body construction, HTTP behavior, and schema extraction.
"""

from __future__ import annotations

from typing import cast

import httpx
import pytest
from nemo_platform import AsyncNeMoPlatform
from nemo_platform_plugin.job import NemoJob
from nemo_platform_plugin.scheduler import NemoJobScheduler
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Fixture jobs
# ---------------------------------------------------------------------------


class _LegacyRawJob(NemoJob):
    """No schema declared — expects the raw dict unchanged."""

    name = "legacy-raw"
    description = "Legacy job without spec_schema."

    def run(self, config: dict) -> dict:
        return {"got": config}


# ---------------------------------------------------------------------------
# submit_remote — URL building, body shaping, HTTP POST (MR 1.3)
# ---------------------------------------------------------------------------


def _mock_transport(capture: dict) -> httpx.MockTransport:
    """Build a transport that captures the request and returns a canned job."""

    def handler(request: httpx.Request) -> httpx.Response:
        capture["url"] = str(request.url)
        capture["method"] = request.method
        capture["body"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"id": "job-123", "status": "queued"})

    return httpx.MockTransport(handler)


class _NamespacedJob(NemoJob):
    """A job defined in a module whose top-level package shapes the API segment."""

    name = "example"


# Force the module on these fixture classes so URL construction sees a stable
# ``{api}`` segment regardless of how pytest rewrote the test module path.
# This mirrors what real plugin jobs get from `<plugin_name>.jobs.<name>`.
_NamespacedJob.__module__ = "my_tests_plugin.jobs.example"


class _CollectionOverrideJob(NemoJob):
    name = "custom"
    job_collection_path = "/custom-jobs"


_CollectionOverrideJob.__module__ = "my_tests_plugin.jobs.custom"


class TestSubmitRemoteURL:
    def test_default_endpoint_applied(self) -> None:
        scheduler = NemoJobScheduler()
        url = scheduler._build_submit_url(
            _NamespacedJob,
            base_url="https://nmp.test",
            workspace="ws-a",
        )
        assert url == "https://nmp.test/apis/my-tests-plugin/v2/workspaces/ws-a/jobs/example"

    def test_job_collection_path_override_honored(self) -> None:
        scheduler = NemoJobScheduler()
        url = scheduler._build_submit_url(
            _CollectionOverrideJob,
            base_url="https://nmp.test",
            workspace="ws-a",
        )
        assert url == "https://nmp.test/apis/my-tests-plugin/v2/workspaces/ws-a/custom-jobs"

    def test_missing_base_url_raises(self) -> None:
        scheduler = NemoJobScheduler()
        with pytest.raises(ValueError, match="requires base_url"):
            scheduler._build_submit_url(_NamespacedJob, base_url=None, workspace="ws")


class TestApiSegmentFor:
    """Cover ``_api_segment_for``, which builds the ``{api}`` portion of submit URLs.

    The platform mounts each plugin's job routes under the ``<plugin>``
    half of its ``nemo.jobs`` entry-point key (``<plugin>.<job>``), so
    the scheduler has to derive the same prefix or every ``submit``
    404s. The authoritative source is the registered entry-point —
    module paths are only consulted when the job isn't installed
    (in-process tests, scratch invocations).
    """

    def test_uses_registered_entry_point_key(self, monkeypatch) -> None:
        from nemo_platform_plugin.scheduler import _api_segment_for

        class _J(NemoJob):
            name = "evaluate"

        # Simulate ``agents.evaluate`` entry-point binding for a class
        # whose package layout (``nemo_agents_plugin``) would otherwise
        # produce ``agents-plugin`` — the URL the platform doesn't mount.
        _J.__module__ = "nemo_agents_plugin.jobs.evaluate_agent"
        monkeypatch.setattr(
            "nemo_platform_plugin.discovery.discover_jobs",
            lambda: {"agents.evaluate": _J},
        )
        assert _api_segment_for(_J) == "agents"

    def test_falls_back_to_module_when_not_registered(self, monkeypatch) -> None:
        from nemo_platform_plugin.scheduler import _api_segment_for

        class _J(NemoJob):
            name = "say-hello"

        # No entry-point match → module-name fallback. The fallback
        # keeps ``_plugin``; an unregistered class in a
        # ``nemo_<name>_plugin`` package surfaces the suffix so the
        # scheduler fails loudly rather than 404ing against the wrong URL.
        _J.__module__ = "nemo_example_plugin.jobs.say_hello"
        monkeypatch.setattr("nemo_platform_plugin.discovery.discover_jobs", lambda: {})
        assert _api_segment_for(_J) == "example-plugin"

    def test_fallback_strips_nemo_prefix(self, monkeypatch) -> None:
        from nemo_platform_plugin.scheduler import _api_segment_for

        class _J(NemoJob):
            name = "evaluate"

        # ``nemo_evaluator`` (no ``_plugin``) strips just ``nemo_``.
        _J.__module__ = "nemo_evaluator.jobs.evaluate"
        monkeypatch.setattr("nemo_platform_plugin.discovery.discover_jobs", lambda: {})
        assert _api_segment_for(_J) == "evaluator"

    def test_handles_missing_nemo_prefix(self, monkeypatch) -> None:
        from nemo_platform_plugin.scheduler import _api_segment_for

        class _J(NemoJob):
            name = "x"

        # In-tree code outside ``nemo_*`` keeps its module name as-is
        # (kebab-cased) so tests with inline classes still produce a
        # stable, predictable segment.
        _J.__module__ = "tests.fixtures.things"
        monkeypatch.setattr("nemo_platform_plugin.discovery.discover_jobs", lambda: {})
        assert _api_segment_for(_J) == "tests"


class TestSubmitRemoteBody:
    def test_body_carries_spec_profile_options_and_metadata(self) -> None:
        scheduler = NemoJobScheduler()
        body = scheduler._build_submit_body(
            {"num_records": 100},
            profile="research",
            options={"slurm": {"nodes": 4}},
            metadata={"name": "nightly", "project": "dd-prod"},
        )
        assert body == {
            "name": "nightly",
            "project": "dd-prod",
            "spec": {"num_records": 100},
            "profile": "research",
            "options": {"slurm": {"nodes": 4}},
        }

    def test_body_omits_profile_when_none(self) -> None:
        scheduler = NemoJobScheduler()
        body = scheduler._build_submit_body({"x": 1}, profile=None, options=None, metadata=None)
        assert body == {"spec": {"x": 1}}

    def test_body_omits_empty_options(self) -> None:
        scheduler = NemoJobScheduler()
        body = scheduler._build_submit_body({"x": 1}, profile="p", options={}, metadata=None)
        assert body == {"spec": {"x": 1}, "profile": "p"}


class TestSubmitRemoteHTTP:
    def test_posts_to_plugin_service_and_returns_response(self) -> None:
        capture: dict = {}
        client = httpx.Client(transport=_mock_transport(capture))
        scheduler = NemoJobScheduler()

        result = scheduler.submit_remote(
            _NamespacedJob,
            {"foo": "bar"},
            base_url="https://nmp.test",
            workspace="ws-a",
            profile="research",
            options={"slurm": {"nodes": 4}},
            metadata={"name": "sub-1"},
            http_client=client,
        )

        assert result == {"id": "job-123", "status": "queued"}
        assert capture["method"] == "POST"
        assert capture["url"] == "https://nmp.test/apis/my-tests-plugin/v2/workspaces/ws-a/jobs/example"
        # Body contents — spec, profile, options, and the metadata envelope.
        import json as _json

        body = _json.loads(capture["body"])
        assert body["spec"] == {"foo": "bar"}
        assert body["profile"] == "research"
        assert body["options"] == {"slurm": {"nodes": 4}}
        assert body["name"] == "sub-1"

    def test_http_error_propagates(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(422, json={"error": "bad spec"})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        scheduler = NemoJobScheduler()
        with pytest.raises(httpx.HTTPStatusError):
            scheduler.submit_remote(
                _NamespacedJob,
                {},
                base_url="https://nmp.test",
                http_client=client,
            )


# ---------------------------------------------------------------------------
# explain — local schema extraction (MR 1.4a)
# ---------------------------------------------------------------------------


class _ExplainSpec(BaseModel):
    name: str
    count: int = 1


class _ExplainJob(NemoJob):
    name = "example"
    spec_schema = _ExplainSpec


_ExplainJob.__module__ = "my_tests_plugin.jobs.example"


class _ExplainInputSpec(BaseModel):
    raw: str


class _ExplainInputJob(NemoJob):
    name = "example-in"
    spec_schema = _ExplainSpec
    input_spec_schema = _ExplainInputSpec


_ExplainInputJob.__module__ = "my_tests_plugin.jobs.example_in"


class _NoSchemaJob(NemoJob):
    name = "raw"  # no spec_schema declared


_NoSchemaJob.__module__ = "my_tests_plugin.jobs.raw"


class TestExplain:
    def test_reads_spec_schema_from_pydantic_locally(self) -> None:
        """No network hop — spec_schema comes from the in-hand NemoJob class."""
        bundle = NemoJobScheduler().explain(_ExplainJob, profile="research")

        assert bundle["job_key"].endswith(".example")
        # endpoint is an illustrative template with {workspace} left as a
        # literal placeholder — explain doesn't POST anywhere.
        assert bundle["endpoint"] == "/apis/my-tests-plugin/v2/workspaces/{workspace}/jobs/example"
        assert bundle["profile"] == "research"
        assert bundle["profile_providers"] == []  # MR 1.4b fills this
        assert bundle["options"] == {}  # MR 1.4b / phase 2 fills this

        spec = bundle["spec_schema"]
        assert spec is not None
        assert spec["type"] == "object"
        assert set(spec["properties"]) == {"name", "count"}
        assert spec["required"] == ["name"]
        assert bundle["input_spec_schema"] is None

    def test_returns_input_spec_schema_when_declared(self) -> None:
        bundle = NemoJobScheduler().explain(_ExplainInputJob)

        assert bundle["spec_schema"] is not None
        inp = bundle["input_spec_schema"]
        assert inp is not None
        assert set(inp["properties"]) == {"raw"}

    def test_returns_none_schemas_when_job_declares_no_spec_schema(self) -> None:
        """Jobs that haven't declared a schema get None — explain still renders."""
        bundle = NemoJobScheduler().explain(_NoSchemaJob)

        assert bundle["spec_schema"] is None
        assert bundle["input_spec_schema"] is None
        assert bundle["endpoint"].endswith("/jobs/raw")

    def test_works_without_any_network_context(self) -> None:
        """explain takes no base_url / cluster / http_client — pure local read."""
        bundle = NemoJobScheduler().explain(_ExplainJob)

        # Endpoint is always rendered with the {workspace} placeholder;
        # there is no --workspace flag on explain.
        assert "{workspace}" in bundle["endpoint"]


# ---------------------------------------------------------------------------
# compile() base class marker (interface extension from 1.2b)
# ---------------------------------------------------------------------------


class _DummySpec(BaseModel):
    """Placeholder BaseModel for tests that only care the call raises."""


class TestCompileMarker:
    def test_compile_raises_when_not_overridden(self) -> None:
        # ``compile`` is an ``async classmethod`` now — drive via
        # ``asyncio.run`` so the marker raises in async context. The base
        # marker raises before reading any arg; the spec value is
        # immaterial, but it must be a BaseModel to satisfy the type.
        import asyncio

        with pytest.raises(NotImplementedError, match="must override compile"):
            asyncio.run(
                _LegacyRawJob.compile(
                    workspace="ws",
                    spec=_DummySpec(),
                    entity_client=None,
                    job_name=None,
                    async_sdk=cast(AsyncNeMoPlatform, None),
                )
            )
