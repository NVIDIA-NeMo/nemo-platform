# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CRUD + read-side tests for the annotations endpoint."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

ANN_BASE = "/apis/intake/v2/workspaces/default/annotations"


def _feedback_body(**overrides: Any) -> dict:
    body = {
        "span_id": "span-1",
        "session_id": "session-A",
        "kind": "feedback",
        "value_text": "positive",
    }
    body.update(overrides)
    return body


def _note_body(**overrides: Any) -> dict:
    body = {
        "span_id": "span-1",
        "session_id": "session-A",
        "kind": "note",
        "text": "The model invented a tool that doesn't exist.",
    }
    body.update(overrides)
    return body


def _label_body(**overrides: Any) -> dict:
    body = {
        "span_id": "span-1",
        "session_id": "session-A",
        "kind": "label",
        "value_text": "regression",
    }
    body.update(overrides)
    return body


def _metadata_body(**overrides: Any) -> dict:
    body = {
        "span_id": "span-1",
        "session_id": "session-A",
        "kind": "metadata",
        "metadata": {"linked_issue": "FP-204", "severity": "high"},
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# Create / read / list
# ---------------------------------------------------------------------------


def test_create_feedback_annotation(client: TestClient):
    response = client.post(ANN_BASE, json=_feedback_body())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["span_id"] == "span-1"
    assert payload["session_id"] == "session-A"
    assert payload["kind"] == "feedback"
    assert payload["value_text"] == "positive"
    assert payload["annotation_id"].startswith("ann-")
    assert "value_numeric" not in payload  # not populated; response_model_exclude_none

    fetched = client.get(f"{ANN_BASE}/{payload['annotation_id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["annotation_id"] == payload["annotation_id"]


def test_create_label_categorical_no_name(client: TestClient):
    response = client.post(ANN_BASE, json=_label_body())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["kind"] == "label"
    assert payload["value_text"] == "regression"
    assert "name" not in payload


def test_create_label_with_name_and_numeric_value(client: TestClient):
    body = _label_body(name="helpfulness", value_text=None, value_numeric=4)
    body.pop("value_text")  # remove the default
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["name"] == "helpfulness"
    assert payload["value_numeric"] == 4


def test_create_note(client: TestClient):
    response = client.post(ANN_BASE, json=_note_body())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["kind"] == "note"
    assert payload["text"].startswith("The model invented")


def test_create_metadata(client: TestClient):
    response = client.post(ANN_BASE, json=_metadata_body())
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["kind"] == "metadata"
    assert payload["metadata"] == {"linked_issue": "FP-204", "severity": "high"}


def test_create_session_level_annotation(client: TestClient):
    body = _feedback_body()
    del body["span_id"]
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert "span_id" not in payload  # session-only
    assert payload["session_id"] == "session-A"


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def test_feedback_rejects_invalid_value(client: TestClient):
    body = _feedback_body(value_text="meh")
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


def test_feedback_rejects_extra_fields(client: TestClient):
    body = _feedback_body(text="this should be a note")
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


def test_label_numeric_requires_name(client: TestClient):
    body = _label_body()
    body.pop("value_text")
    body["value_numeric"] = 4
    # no name set
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


def test_note_requires_text(client: TestClient):
    body = _note_body()
    body.pop("text")
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


def test_metadata_requires_non_empty_dict(client: TestClient):
    body = _metadata_body()
    body["metadata"] = {}
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


def test_unknown_kind_rejected(client: TestClient):
    body = _feedback_body(kind="thumb")  # legacy name we deliberately rejected
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# Attach-after-ingest behavior + missing target permissive policy
# ---------------------------------------------------------------------------


def test_attach_to_nonexistent_span_is_permitted(client: TestClient):
    """Loose target policy: posting an annotation referencing a span_id that
    doesn't exist in the spans table is accepted. Matches evaluator_results."""

    body = _note_body(span_id="span-that-does-not-exist", session_id="session-fresh")
    response = client.post(ANN_BASE, json=body)
    assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Multiple annotations per target
# ---------------------------------------------------------------------------


def test_multiple_annotations_per_target(client: TestClient):
    session_id = "session-multi-target"
    span_id = "span-multi-target"
    for body in [
        _feedback_body(span_id=span_id, session_id=session_id, value_text="negative"),
        _note_body(span_id=span_id, session_id=session_id, text="first note"),
        _note_body(span_id=span_id, session_id=session_id, text="second note from same user"),
        _label_body(span_id=span_id, session_id=session_id, value_text="needs-review"),
    ]:
        response = client.post(ANN_BASE, json=body)
        assert response.status_code == 201, response.text

    listed = client.get(ANN_BASE, params={"filter[span_id]": span_id, "page_size": 20})
    assert listed.status_code == 200, listed.text
    data = listed.json()["data"]
    assert len(data) == 4
    kinds = {item["kind"] for item in data}
    assert kinds == {"feedback", "note", "label"}


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def test_filter_by_kind(client: TestClient):
    session_id = "session-filter-kind"
    span_id = "span-filter-kind"
    client.post(ANN_BASE, json=_feedback_body(span_id=span_id, session_id=session_id))
    client.post(ANN_BASE, json=_note_body(span_id=span_id, session_id=session_id))
    client.post(ANN_BASE, json=_note_body(span_id=span_id, session_id=session_id, text="another note"))

    response = client.get(ANN_BASE, params={"filter[session_id]": session_id, "filter[kind]": "note"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 2
    assert {item["kind"] for item in data} == {"note"}


def test_filter_by_name(client: TestClient):
    session_id = "session-filter-name"
    span_id = "span-filter-name"
    body_a = _label_body(span_id=span_id, session_id=session_id, name="tone", value_text="professional")
    body_b = _label_body(span_id=span_id, session_id=session_id, name="category", value_text="regression")
    client.post(ANN_BASE, json=body_a)
    client.post(ANN_BASE, json=body_b)

    response = client.get(ANN_BASE, params={"filter[session_id]": session_id, "filter[name]": "tone"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "tone"


# ---------------------------------------------------------------------------
# Per-span convenience endpoint
# ---------------------------------------------------------------------------


def test_list_annotations_for_span_endpoint(client: TestClient):
    session_id = "session-span-list"
    span_id = "span-with-annotations"
    client.post(ANN_BASE, json=_feedback_body(span_id=span_id, session_id=session_id))
    client.post(ANN_BASE, json=_note_body(span_id=span_id, session_id=session_id))

    response = client.get(f"/apis/intake/v2/workspaces/default/spans/{span_id}/annotations")
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data) == 2


# ---------------------------------------------------------------------------
# PATCH
# ---------------------------------------------------------------------------


def test_patch_updates_value(client: TestClient):
    created = client.post(ANN_BASE, json=_feedback_body()).json()
    annotation_id = created["annotation_id"]

    patched = client.patch(
        f"{ANN_BASE}/{annotation_id}",
        json={"value_text": "negative"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["value_text"] == "negative"

    # Fetch confirms the new value
    fetched = client.get(f"{ANN_BASE}/{annotation_id}")
    assert fetched.json()["value_text"] == "negative"


def test_patch_rejects_invalid_merged_state(client: TestClient):
    created = client.post(ANN_BASE, json=_feedback_body()).json()
    annotation_id = created["annotation_id"]

    # Try to patch a feedback annotation to a non-feedback value
    response = client.patch(
        f"{ANN_BASE}/{annotation_id}",
        json={"value_text": "regression"},
    )
    assert response.status_code == 422, response.text


def test_patch_missing_annotation_returns_404(client: TestClient):
    response = client.patch(f"{ANN_BASE}/ann-does-not-exist", json={"value_text": "negative"})
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


def test_delete_annotation(client: TestClient):
    created = client.post(ANN_BASE, json=_note_body()).json()
    annotation_id = created["annotation_id"]

    deleted = client.delete(f"{ANN_BASE}/{annotation_id}")
    assert deleted.status_code == 204, deleted.text

    fetched = client.get(f"{ANN_BASE}/{annotation_id}")
    assert fetched.status_code == 404, fetched.text


def test_delete_missing_annotation_returns_404(client: TestClient):
    response = client.delete(f"{ANN_BASE}/ann-does-not-exist")
    assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# Get missing annotation
# ---------------------------------------------------------------------------


def test_get_missing_annotation_returns_404(client: TestClient):
    response = client.get(f"{ANN_BASE}/ann-does-not-exist")
    assert response.status_code == 404, response.text
