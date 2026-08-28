# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pandas as pd
from anonymizer.config.anonymizer_config import AnonymizerConfig
from anonymizer.config.replace_strategies import Redact
from nemo_anonymizer_plugin.app.input import AnonymizerInputSpec
from nemo_anonymizer_plugin.app.task_config import PreviewRequest
from nemo_anonymizer_plugin.functions.preview import LogFrame, PreviewDatasetFrame, TraceDatasetFrame
from nemo_anonymizer_plugin.sdk import display as display_module
from nemo_anonymizer_plugin.sdk.errors import AnonymizerClientError, AnonymizerConfigValidationError
from nemo_anonymizer_plugin.sdk.resources import (
    AnonymizerPreviewResult,
    AnonymizerResource,
    _get_error,
    _PreviewFrameCollector,
)
from nemo_platform_plugin.functions.frames import Done


def _status_error(status_code: int, content: bytes) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://platform.test/apis/anonymizer/v2/workspaces/default/preview")
    response = httpx.Response(status_code, content=content, request=request)
    return httpx.HTTPStatusError("request failed", request=request, response=response)


def test_get_error_uses_json_detail_for_validation_errors() -> None:
    error = _get_error(_status_error(422, b'{"detail":"invalid config"}'))

    assert isinstance(error, AnonymizerConfigValidationError)
    assert str(error) == "Config validation failed!\ninvalid config"


def test_get_error_logs_invalid_json_and_keeps_text_detail(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="nemo_anonymizer_plugin.sdk.resources")

    error = _get_error(_status_error(500, b"server exploded"))

    assert isinstance(error, AnonymizerClientError)
    assert str(error) == "Something went wrong!\nserver exploded"
    assert "Anonymizer error response body is not JSON." in caplog.text


class BrokenStream(httpx.SyncByteStream):
    def __iter__(self):
        raise httpx.ReadError("stream failed")


def test_get_error_logs_response_read_failures(caplog) -> None:
    caplog.set_level(logging.DEBUG, logger="nemo_anonymizer_plugin.sdk.resources")
    request = httpx.Request("POST", "https://platform.test/apis/anonymizer/v2/workspaces/default/preview")
    response = httpx.Response(500, stream=BrokenStream(), request=request)
    status_error = httpx.HTTPStatusError("request failed", request=request, response=response)

    error = _get_error(status_error)

    assert isinstance(error, AnonymizerClientError)
    assert str(error) == "Something went wrong!\nInternal Server Error"
    assert "Failed to read Anonymizer error response body." in caplog.text
    assert "Cannot parse Anonymizer error response JSON because the body was not read." in caplog.text


def test_preview_collector_preserves_original_text_column_metadata() -> None:
    collector = _PreviewFrameCollector()

    collector.accept(TraceDatasetFrame(records=[{"body": "Alice"}], original_text_column="body"))

    assert collector.trace_dataset is not None
    assert collector.trace_dataset.attrs["original_text_column"] == "body"


def test_preview_result_display_record_matches_upstream_display_cycle(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    trace = pd.DataFrame([{"body": "Alice"}, {"body": "Bob"}])
    trace.attrs["original_text_column"] = "body"
    result = AnonymizerPreviewResult(dataset=pd.DataFrame(), trace_dataset=trace)

    def fake_render_record_html(row, record_index: int | None, resolved_text_column: str | None) -> str:
        captured["row"] = row
        captured["record_index"] = record_index
        captured["resolved_text_column"] = resolved_text_column
        return "<div>ok</div>"

    monkeypatch.setattr(display_module, "render_record_html", fake_render_record_html)

    result.display_record()

    assert captured["record_index"] == 0
    assert captured["resolved_text_column"] == "body"
    assert result._display_cycle_index == 1


def test_preview_stream_decodes_typed_frames() -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def raise_for_status(self) -> None:
            pass

        def iter_lines(self) -> list[str]:
            return [
                '{"kind":"log","level":"info","message":"loading models"}',
                '{"kind":"preview_dataset","records":[{"text":"[REDACTED_PERSON]"}]}',
                '{"kind":"done"}',
            ]

    class Client:
        def stream(self, method: str, url: str, **kwargs: object) -> Response:
            calls.append((method, url, kwargs))
            return Response()

    platform = SimpleNamespace(
        base_url="https://platform.test",
        workspace="default",
        default_headers={"Authorization": "Bearer token"},
        _client=Client(),
    )
    resource = AnonymizerResource(cast(Any, platform))
    request = PreviewRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source="inputs#records.csv"),
        num_records=1,
    )

    frames = list(resource.preview_stream(request, workspace="team/a"))

    assert isinstance(frames[0], LogFrame)
    assert isinstance(frames[1], PreviewDatasetFrame)
    assert isinstance(frames[2], Done)
    assert len(calls) == 1
    method, url, kwargs = calls[0]
    assert method == "POST"
    assert url == "https://platform.test/apis/anonymizer/v2/workspaces/team%2Fa/preview"
    assert kwargs["headers"] == {"Authorization": "Bearer token"}
    body = cast(dict[str, Any], kwargs["json"])
    assert body["config"]["replace"]["kind"] == "redact"
    assert body["config"]["replace"]["format_template"] == "[REDACTED_{label}]"
    assert body["data"]["source"] == "inputs#records.csv"
    assert body["num_records"] == 1


def test_preview_collects_frames_from_preview_stream(monkeypatch) -> None:
    platform = SimpleNamespace(
        base_url="https://platform.test",
        workspace="default",
        default_headers={},
        _client=object(),
    )
    resource = AnonymizerResource(cast(Any, platform))
    request = PreviewRequest(
        config=AnonymizerConfig(replace=Redact()),
        data=AnonymizerInputSpec(source="inputs#records.csv"),
        num_records=1,
    )
    captured: dict[str, object] = {}

    def fake_preview_stream(request: PreviewRequest, *, workspace: str | None = None):
        captured["request"] = request
        captured["workspace"] = workspace
        yield PreviewDatasetFrame(records=[{"text": "[REDACTED_PERSON]"}])
        yield TraceDatasetFrame(records=[{"text": "Alice"}], original_text_column="text")
        yield Done()

    monkeypatch.setattr(resource, "preview_stream", fake_preview_stream)

    result = resource.preview(request, workspace="team-a")

    assert captured == {"request": request, "workspace": "team-a"}
    assert result.dataset.to_dict(orient="records") == [{"text": "[REDACTED_PERSON]"}]
    assert result.trace_dataset.attrs["original_text_column"] == "text"
