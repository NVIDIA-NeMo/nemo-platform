# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

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
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle, bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric


class _FakeFilesets:
    def __init__(self, store: dict[tuple[str, str], dict[str, bytes]]) -> None:
        self._store = store

    async def create(self, *, workspace: str | None = None, name: str, description: str) -> object:
        del description
        self._store.setdefault((workspace or "default", name), {})
        return object()

    async def delete(self, name: str, *, workspace: str | None = None) -> object:
        self._store.pop((workspace or "default", name), None)
        return object()


class _FakeFiles:
    filesets: _FakeFilesets

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, bytes]] = {}
        self.upload_error: Exception | None = None
        self.filesets = _FakeFilesets(self._store)

    async def upload_content(
        self,
        *,
        content: bytes,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> object:
        if self.upload_error is not None:
            raise self.upload_error
        if fileset is None:
            raise ValueError("fileset is required")
        self._store.setdefault((workspace or "default", fileset), {})[remote_path] = bytes(content)
        return object()

    async def download_content(
        self,
        *,
        remote_path: str,
        fileset: str | None = None,
        workspace: str | None = None,
    ) -> bytes:
        if fileset is None:
            raise ValueError("fileset is required")
        return self._store[(workspace or "default", fileset)][remote_path]


class _FakePlatform:
    files: _FakeFiles

    def __init__(self, files: _FakeFiles | None = None) -> None:
        self.files = files or _FakeFiles()


def _sample_bundle() -> MetricBundle:
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    return bundle_metric(metric, CloudpickleMetricBundlePackager())


def _fake_platform(files: _FakeFiles | None = None) -> _FakePlatform:
    return _FakePlatform(files)


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
    fake_files = _FakeFiles()
    platform = _fake_platform(fake_files)
    bundle = _sample_bundle()

    ref1 = await store_bundle(platform, "default", "my-metric", bundle)
    ref2 = await store_bundle(platform, "default", "my-metric", bundle)

    assert ref1.startswith("default/metric-bundle.")
    assert ref1.endswith(f"#{BUNDLE_FILENAME}")
    assert ref1 != ref2


async def test_store_fileset_name_stays_within_limit_for_long_metric_name() -> None:
    fake_files = _FakeFiles()
    bundle = _sample_bundle()
    long_name = "m" * 255

    ref = await store_bundle(_fake_platform(fake_files), "default", long_name, bundle)

    _, fileset, _ = parse_bundle_ref(ref)
    assert len(fileset) <= 255


async def test_store_cleans_up_fileset_on_upload_failure() -> None:
    fake_files = _FakeFiles()
    bundle = _sample_bundle()

    fake_files.upload_error = RuntimeError("network blip during upload")

    with pytest.raises(MetricBundleStorageError):
        await store_bundle(_fake_platform(fake_files), "default", "my-metric", bundle)

    assert [key for key in fake_files._store if key[1].startswith(FILESET_PREFIX)] == []


async def test_store_then_load_round_trips_bundle() -> None:
    fake_files = _FakeFiles()
    platform = _fake_platform(fake_files)
    bundle = _sample_bundle()

    ref = await store_bundle(platform, "default", "my-metric", bundle)
    loaded = await load_bundle(platform, ref, expected_digest=bundle.payload.digest)

    assert loaded.metric_type == bundle.metric_type
    assert loaded.payload.digest == bundle.payload.digest


async def test_load_rejects_digest_mismatch() -> None:
    fake_files = _FakeFiles()
    platform = _fake_platform(fake_files)
    bundle = _sample_bundle()

    ref = await store_bundle(platform, "default", "my-metric", bundle)
    with pytest.raises(MetricBundleStorageError, match="digest mismatch"):
        await load_bundle(platform, ref, expected_digest="deadbeef")


async def test_load_rejects_corrupt_bundle() -> None:
    fake_files = _FakeFiles()
    fake_files._store[("default", "metric-bundle.deadbeef")] = {"bundle.json": b"not a bundle"}

    with pytest.raises(MetricBundleStorageError, match="corrupt or unreadable"):
        await load_bundle(_fake_platform(fake_files), "default/metric-bundle.deadbeef#bundle.json")


async def test_load_wraps_download_failure() -> None:
    fake_files = _FakeFiles()

    with pytest.raises(MetricBundleStorageError, match="failed to download metric bundle"):
        await load_bundle(_fake_platform(fake_files), "default/metric-bundle.missing#bundle.json")


async def test_delete_by_ref_removes_only_that_fileset() -> None:
    fake_files = _FakeFiles()
    platform = _fake_platform(fake_files)
    bundle = _sample_bundle()

    ref1 = await store_bundle(platform, "default", "my-metric", bundle)
    ref2 = await store_bundle(platform, "default", "my-metric", bundle)
    await delete_bundle_by_ref(platform, ref1)

    _, fileset1, _ = parse_bundle_ref(ref1)
    _, fileset2, _ = parse_bundle_ref(ref2)
    assert ("default", fileset1) not in fake_files._store
    assert ("default", fileset2) in fake_files._store
