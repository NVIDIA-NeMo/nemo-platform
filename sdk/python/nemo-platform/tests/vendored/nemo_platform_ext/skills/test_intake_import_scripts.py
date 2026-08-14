# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import base64
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "packages/nemo_platform_ext/src/nemo_platform_ext/skills/nemo-intake/scripts"
FIXTURES = Path(__file__).parent / "fixtures/observability"
sys.path.insert(0, str(SCRIPTS))


def _payload(provider: str) -> dict[str, Any]:
    if provider == "mlflow":
        return _json("mlflow-trace.json")
    if provider == "langsmith":
        return {**_json("langsmith-runs.json"), **_json("langsmith-feedback.json")}
    if provider == "phoenix":
        return {"spans": _json("phoenix-spans.json")["data"], **_json("phoenix-annotations.json")}
    if provider == "braintrust":
        return _json("braintrust-project-log.json")
    raise AssertionError(provider)


def _bundle(provider: str, *, include_feedback: bool = True) -> Any:
    module = importlib.import_module(f"import_{provider}")
    mapper = getattr(module, f"map_{provider}_export")
    return mapper(_payload(provider), project="fixture", include_feedback=include_feedback)


@pytest.mark.parametrize("provider", ["mlflow", "langsmith", "phoenix", "braintrust"])
def test_official_provider_fixture_maps_to_golden_without_field_gaps(provider: str) -> None:
    bundle = _bundle(provider)
    golden = _json(f"expected-{provider}.json")

    bundle.validate()
    assert len(bundle.spans) == golden["span_count"]
    span = bundle.spans[0]
    for key, value in golden["span"].items():
        assert span[key] == value
    for expectation in golden["raw_paths"]:
        assert _at_path(span["attributes"], expectation["path"]) == expectation["value"]
    assert [item["name"] for item in bundle.evaluator_results] == golden["evaluator_names"]
    assert [item["kind"] for item in bundle.annotations] == golden["annotation_kinds"]

    for coverage in bundle.coverage:
        dispositions = (coverage.mapped_fields, coverage.preserved_fields, coverage.ignored_fields)
        assert set().union(*dispositions) == coverage.all_fields
        assert not any(left & right for index, left in enumerate(dispositions) for right in dispositions[index + 1 :])


@pytest.mark.parametrize("provider", ["mlflow", "langsmith", "phoenix", "braintrust"])
def test_include_feedback_false_suppresses_all_signal_writes(provider: str) -> None:
    bundle = _bundle(provider, include_feedback=False)

    assert bundle.evaluator_results == []
    assert bundle.annotations == []
    assert all(f"{provider}.signals" not in span["attributes"] for span in bundle.spans)


def test_braintrust_repeated_event_versions_keep_latest_first() -> None:
    payload = _payload("braintrust")
    stale = {**payload["events"][0], "output": {"answer": "stale"}}
    payload["events"].append(stale)
    module = importlib.import_module("import_braintrust")

    bundle = module.map_braintrust_export(payload, project="fixture", include_feedback=True)

    assert len(bundle.spans) == 1
    assert bundle.spans[0]["output"] == {"answer": "Paris"}


def test_braintrust_epoch_zero_start_is_not_replaced_by_created_time() -> None:
    payload = _payload("braintrust")
    payload["events"][0]["metrics"] = {"start": 0, "duration": 1}
    module = importlib.import_module("import_braintrust")

    bundle = module.map_braintrust_export(payload, project="fixture", include_feedback=False)

    assert bundle.spans[0]["started_at"] == "1970-01-01T00:00:00+00:00"
    assert bundle.spans[0]["ended_at"] == "1970-01-01T00:00:01+00:00"


def test_braintrust_fetch_does_not_assume_created_time_page_order(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("import_braintrust")
    responses = [
        _Response({"events": [{"id": "old", "created": "2025-01-01T00:00:00Z"}], "cursor": "next"}),
        _Response({"events": [{"id": "in-range", "created": "2026-08-01T12:00:00Z"}]}),
    ]
    get = Mock(side_effect=responses)
    monkeypatch.setattr(module.requests, "get", get)
    monkeypatch.setenv("BRAINTRUST_API_KEY", "test-key")
    args = argparse.Namespace(
        braintrust_base_url="https://api.braintrust.dev",
        project="project-id",
        since=datetime(2026, 8, 1, tzinfo=timezone.utc),
        until=datetime(2026, 8, 2, tzinfo=timezone.utc),
    )

    payload = module.fetch_braintrust(args)

    assert [event["id"] for event in payload["events"]] == ["in-range"]
    assert get.call_count == 2


def test_mlflow_native_trace_id_fallback_is_canonicalized() -> None:
    payload = _payload("mlflow")
    native_trace_id = bytes(range(16))
    payload["traces"][0]["info"]["trace_id"] = ""
    for span in payload["traces"][0]["data"]["spans"]:
        span["trace_id"] = base64.b64encode(native_trace_id).decode()
    module = importlib.import_module("import_mlflow")

    bundle = module.map_mlflow_export(payload, project="fixture", include_feedback=True)

    assert {span["trace_id"] for span in bundle.spans} == {native_trace_id.hex()}
    assert bundle.evaluator_results[0]["span_id"] in {span["span_id"] for span in bundle.spans}


def test_intake_writer_uses_sdk_factory_for_context_and_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    common = importlib.import_module("_import_common")
    sdk = Mock(base_url="https://platform.example.com", workspace="oauth-workspace")
    sdk._client = Mock()
    factory = Mock(return_value=sdk)
    monkeypatch.setattr(common, "create_client", factory)

    writer = common.IntakeWriter(base_url=None, workspace=None)

    assert writer.base_url == "https://platform.example.com"
    assert writer.workspace == "oauth-workspace"
    factory.assert_called_once_with(base_url=None, access_token=None, timeout=60.0, max_retries=0)
    verify_spans = Mock()
    monkeypatch.setattr(writer, "_verify_spans", verify_spans)
    span = {"span_id": "span-1", "trace_id": "trace-1", "started_at": "2026-08-14T12:00:00Z"}

    writer.write(common.ImportBundle(source="langsmith", spans=[span]), batch_size=500)

    sdk.intake.ingest.spans.create.assert_called_once_with(
        workspace="oauth-workspace",
        source="langsmith",
        spans=[span],
    )
    verify_spans.assert_called_once_with([span], source="langsmith")
    writer.close()
    sdk.close.assert_called_once_with()


class _Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200
        self.text = json.dumps(payload)

    def json(self) -> dict[str, Any]:
        return self._payload


def _json(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def _at_path(value: Any, path: list[str | int]) -> Any:
    current = value
    for part in path:
        current = current[part]
    return current
