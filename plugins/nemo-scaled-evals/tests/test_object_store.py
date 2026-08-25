# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Cover the startup bucket provisioner."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from botocore.exceptions import ClientError
from nemo_scaled_evals_plugin.service import ScaledEvalsService
from scaled_evals.api import s3


class _FakeS3:
    """Records calls and replays the ClientError the test asks for."""

    def __init__(self, head_error: str | None, create_error: str | None = None) -> None:
        self._head_error = head_error
        self._create_error = create_error
        self.created: list[str] = []

    def head_bucket(self, Bucket: str) -> None:  # noqa: N803 - boto3 kwarg name
        if self._head_error:
            raise _client_error(self._head_error, "HeadBucket")

    def create_bucket(self, Bucket: str) -> None:  # noqa: N803 - boto3 kwarg name
        if self._create_error:
            raise _client_error(self._create_error, "CreateBucket")
        self.created.append(Bucket)


def _client_error(code: str, operation: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": code}}, operation)


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeS3) -> None:
    monkeypatch.setattr(s3, "_client", lambda *_a, **_k: fake)
    monkeypatch.setattr(s3, "_bucket", lambda: "scaled-evals")
    monkeypatch.setattr(s3, "_using_gcs", lambda: False)


def test_bucket_is_created_only_when_missing_and_refusal_is_tolerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Already there: must not attempt a create.
    existing = _FakeS3(head_error=None)
    _install(monkeypatch, existing)
    assert s3.ensure_bucket() == "scaled-evals"
    assert existing.created == []

    # Missing: create it, so a fresh RustFS volume needs no manual `s3 mb`.
    missing = _FakeS3(head_error="404")
    _install(monkeypatch, missing)
    assert s3.ensure_bucket() == "scaled-evals"
    assert missing.created == ["scaled-evals"]

    # Lost the race with another replica: benign, not an error.
    raced = _FakeS3(head_error="404", create_error="BucketAlreadyOwnedByYou")
    _install(monkeypatch, raced)
    assert s3.ensure_bucket() == "scaled-evals"

    # Denied by a managed store that pre-provisions buckets: surfaces to the caller,
    # which logs it and lets /v1/readyz report object_store.
    denied = _FakeS3(head_error="403", create_error="AccessDenied")
    _install(monkeypatch, denied)
    with pytest.raises(ClientError):
        s3.ensure_bucket()


def test_startup_survives_an_unreachable_object_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Storage being down must degrade the plugin, not abort platform startup."""

    def explode(*_a: Any, **_k: Any) -> None:
        raise ClientError({"Error": {"Code": "EndpointConnectionError"}}, "HeadBucket")

    monkeypatch.setattr(s3, "ensure_bucket", explode)
    # Keep the database side out of it; this test is about the object store.
    monkeypatch.setattr(ScaledEvalsService, "_apply_migrations", lambda _self: None)

    asyncio.run(ScaledEvalsService().on_startup())
