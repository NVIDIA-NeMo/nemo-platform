# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

import httpx
import pandas as pd
from nemo_anonymizer_plugin.functions.preview import TraceDatasetFrame
from nemo_anonymizer_plugin.sdk import display as display_module
from nemo_anonymizer_plugin.sdk.errors import AnonymizerClientError, AnonymizerConfigValidationError
from nemo_anonymizer_plugin.sdk.resources import AnonymizerPreviewResult, _get_error, _PreviewFrameCollector


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
