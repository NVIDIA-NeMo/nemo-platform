# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the small error-extraction helper that replaces the legacy
``if "404" in str(e)`` pattern. Because the helper is pure logic over an
``httpx.Response``, it sits naturally as a unit test."""

import httpx
import pytest
from nemo_data_designer_plugin.sdk.errors import (
    DataDesignerClientError,
    DataDesignerJobError,
    extract_http_error_info,
)


def _make_status_error(status_code: int, *, body: str | None = None, json_body: object = None) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", "http://testserver/whatever")
    if json_body is not None:
        response = httpx.Response(status_code, request=request, json=json_body)
    else:
        response = httpx.Response(status_code, request=request, text=body or "")
    return httpx.HTTPStatusError("err", request=request, response=response)


def test_extract_http_error_info_pulls_detail_field_from_json_body() -> None:
    exc = _make_status_error(404, json_body={"detail": "Job result not found"})

    status_code, detail = extract_http_error_info(exc)

    assert status_code == 404
    assert detail == "Job result not found"


def test_extract_http_error_info_falls_back_to_raw_body_when_not_json() -> None:
    exc = _make_status_error(500, body="<html>oh no</html>")

    status_code, detail = extract_http_error_info(exc)

    assert status_code == 500
    assert detail == "<html>oh no</html>"


def test_extract_http_error_info_falls_back_to_raw_body_when_json_lacks_detail() -> None:
    exc = _make_status_error(422, json_body={"errors": ["bad config"]})

    status_code, detail = extract_http_error_info(exc)

    assert status_code == 422
    # Body is JSON but has no string ``detail`` field, so we surface the raw text.
    assert "errors" in detail


def test_extract_http_error_info_ignores_non_string_detail_field() -> None:
    """A ``detail`` field that isn't a string (e.g. a list of validation errors) should
    fall through to the raw body so callers always get a string."""
    exc = _make_status_error(422, json_body={"detail": [{"loc": ["body"], "msg": "field required"}]})

    _, detail = extract_http_error_info(exc)

    assert isinstance(detail, str)
    assert "field required" in detail


def test_data_designer_client_error_carries_status_code() -> None:
    err = DataDesignerJobError("Job result not found", status_code=404)
    assert isinstance(err, DataDesignerClientError)
    assert err.status_code == 404
    assert str(err) == "Job result not found"


def test_data_designer_client_error_status_code_defaults_to_none() -> None:
    """Locally-constructed errors (where there's no upstream HTTP response) carry no status."""
    err = DataDesignerJobError("Current job status is 'cancelled', results are not available.")
    assert err.status_code is None


@pytest.mark.parametrize("status_code", [404, 422, 500])
def test_status_code_round_trips_through_raise_from(status_code: int) -> None:
    """Make sure the status code survives the ``raise X from exc`` pattern used in
    ``_raise_for_status`` / ``_get_error``."""
    cause = _make_status_error(status_code, json_body={"detail": "boom"})
    try:
        raise DataDesignerJobError("boom", status_code=status_code) from cause
    except DataDesignerJobError as e:
        assert e.status_code == status_code
        assert e.__cause__ is cause
