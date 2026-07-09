# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from nemo_evaluator.metric_storage import (
    BUNDLE_FILENAME,
    FILESET_PREFIX,
    MetricBundleStorageError,
    delete_bundle_by_ref,
    load_bundle,
    parse_bundle_ref,
    store_bundle,
)
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeAsyncFilesClient:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, bytes]] = {}

    async def create_fileset(self, *, body, workspace=None, exist_ok=False):
        self._store.setdefault((workspace, body.name), {})
        return AsyncMock(data=lambda: object())

    async def delete_fileset(self, *, name, workspace=None):
        self._store.pop((workspace, name), None)
        return AsyncMock(data=lambda: object())

    async def upload_file(self, *, path, content, workspace, name):
        self._store.setdefault((workspace, name), {})[path] = bytes(content)
        return AsyncMock(data=lambda: object())

    async def download_file(self, *, path, workspace, name):
        return _FakeResponse(self._store[(workspace, name)][path])


def _sample_bundle():
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    return bundle_metric(metric, CloudpickleMetricBundlePackager())


def test_parse_bundle_ref_splits_parts() -> None:
    assert parse_bundle_ref("default/metric-bundle.m.abc#bundle.json") == (
        "default",
        "metric-bundle.m.abc",
        "bundle.json",
    )


@pytest.mark.parametrize("ref", ["no-fragment", "missing-workspace#bundle.json", "ws/fs#"])
def test_parse_bundle_ref_rejects_malformed(ref: str) -> None:
    with pytest.raises(MetricBundleStorageError):
        parse_bundle_ref(ref)


async def test_store_returns_unique_per_metric_ref() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()

    with patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client):
        ref1 = await store_bundle(object(), "default", "my-metric", bundle)
        ref2 = await store_bundle(object(), "default", "my-metric", bundle)

    assert ref1.startswith("default/metric-bundle.")
    assert ref1.endswith(f"#{BUNDLE_FILENAME}")
    assert ref1 != ref2


async def test_store_fileset_name_stays_within_limit_for_long_metric_name() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()
    long_name = "m" * 255

    with patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client):
        ref = await store_bundle(object(), "default", long_name, bundle)

    _, fileset, _ = parse_bundle_ref(ref)
    assert len(fileset) <= 255


async def test_store_cleans_up_fileset_on_upload_failure() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()

    async def _boom(*, path, content, workspace, name):
        raise RuntimeError("network blip during upload")

    fake_client.upload_file = _boom

    with (
        patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client),
        pytest.raises(MetricBundleStorageError),
    ):
        await store_bundle(object(), "default", "my-metric", bundle)

    assert [key for key in fake_client._store if key[1].startswith(FILESET_PREFIX)] == []


async def test_store_then_load_round_trips_bundle() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()

    with patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client):
        ref = await store_bundle(object(), "default", "my-metric", bundle)
        loaded = await load_bundle(object(), ref, expected_digest=bundle.payload.digest)

    assert loaded.metric_type == bundle.metric_type
    assert loaded.payload.digest == bundle.payload.digest


async def test_load_rejects_digest_mismatch() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()

    with (
        patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client),
        pytest.raises(MetricBundleStorageError, match="digest mismatch"),
    ):
        ref = await store_bundle(object(), "default", "my-metric", bundle)
        await load_bundle(object(), ref, expected_digest="deadbeef")


async def test_load_rejects_corrupt_bundle() -> None:
    fake_client = _FakeAsyncFilesClient()
    fake_client._store[("default", "metric-bundle.deadbeef")] = {"bundle.json": b"not a bundle"}

    with (
        patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client),
        pytest.raises(MetricBundleStorageError, match="corrupt or unreadable"),
    ):
        await load_bundle(object(), "default/metric-bundle.deadbeef#bundle.json")


async def test_load_wraps_download_failure() -> None:
    fake_client = _FakeAsyncFilesClient()

    with (
        patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client),
        pytest.raises(MetricBundleStorageError, match="failed to download metric bundle"),
    ):
        await load_bundle(object(), "default/metric-bundle.missing#bundle.json")


async def test_delete_by_ref_removes_only_that_fileset() -> None:
    fake_client = _FakeAsyncFilesClient()
    bundle = _sample_bundle()

    with patch("nemo_evaluator.metric_storage.client_from_platform", return_value=fake_client):
        ref1 = await store_bundle(object(), "default", "my-metric", bundle)
        ref2 = await store_bundle(object(), "default", "my-metric", bundle)
        await delete_bundle_by_ref(object(), ref1)

    _, fileset1, _ = parse_bundle_ref(ref1)
    _, fileset2, _ = parse_bundle_ref(ref2)
    assert ("default", fileset1) not in fake_client._store
    assert ("default", fileset2) in fake_client._store
