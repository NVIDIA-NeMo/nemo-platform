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
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric


class _FakeFile:
    def __init__(self, file_ref: str) -> None:
        self.file_ref = file_ref


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeFilesets:
    def __init__(self, store: dict[tuple[str, str], dict[str, bytes]]) -> None:
        self._store = store

    async def create(self, *, name, workspace, description=None, exist_ok=False):
        self._store.setdefault((workspace, name), {})
        return object()

    async def delete(self, name, *, workspace=None):
        self._store.pop((workspace, name), None)
        return object()


class _FakeFiles:
    def __init__(self, store: dict[tuple[str, str], dict[str, bytes]]) -> None:
        self._store = store
        self.filesets = _FakeFilesets(store)

    async def _upload_file(self, *, path, body, workspace, name):
        self._store.setdefault((workspace, name), {})[path] = bytes(body)
        return _FakeFile(f"{workspace}/{name}#{path}")

    async def _download_file(self, path, *, workspace, name):
        return _FakeResponse(self._store[(workspace, name)][path])


class _FakeSDK:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], dict[str, bytes]] = {}
        self.files = _FakeFiles(self._store)


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
    sdk = _FakeSDK()
    bundle = _sample_bundle()

    ref1 = await store_bundle(sdk, "default", "my-metric", bundle)
    ref2 = await store_bundle(sdk, "default", "my-metric", bundle)

    assert ref1.startswith("default/metric-bundle.")
    assert ref1.endswith(f"#{BUNDLE_FILENAME}")
    # Each upload lands in its own fileset, so a rollback can't clobber another.
    assert ref1 != ref2


async def test_store_fileset_name_stays_within_limit_for_long_metric_name() -> None:
    sdk = _FakeSDK()
    bundle = _sample_bundle()
    long_name = "m" * 255  # MAX_NAME_LENGTH

    ref = await store_bundle(sdk, "default", long_name, bundle)

    _, fileset, _ = parse_bundle_ref(ref)
    # The Files service caps fileset names at 255 chars.
    assert len(fileset) <= 255


async def test_store_cleans_up_fileset_on_upload_failure() -> None:
    sdk = _FakeSDK()
    bundle = _sample_bundle()

    async def _boom(*args, **kwargs):
        raise RuntimeError("network blip during upload")

    sdk.files._upload_file = _boom

    with pytest.raises(MetricBundleStorageError):
        await store_bundle(sdk, "default", "my-metric", bundle)
    # The fileset created just before the failed upload must not be left orphaned.
    assert [key for key in sdk._store if key[1].startswith(FILESET_PREFIX)] == []


async def test_store_then_load_round_trips_bundle() -> None:
    sdk = _FakeSDK()
    bundle = _sample_bundle()

    ref = await store_bundle(sdk, "default", "my-metric", bundle)

    loaded = await load_bundle(sdk, ref, expected_digest=bundle.payload.digest)
    assert loaded.metric_type == bundle.metric_type
    assert loaded.payload.digest == bundle.payload.digest


async def test_load_rejects_digest_mismatch() -> None:
    sdk = _FakeSDK()
    bundle = _sample_bundle()
    ref = await store_bundle(sdk, "default", "my-metric", bundle)

    with pytest.raises(MetricBundleStorageError, match="digest mismatch"):
        await load_bundle(sdk, ref, expected_digest="deadbeef")


async def test_load_rejects_corrupt_bundle() -> None:
    sdk = _FakeSDK()
    # Stored bytes that aren't a valid serialized MetricBundle.
    sdk._store[("default", "metric-bundle.deadbeef")] = {"bundle.json": b"not a bundle"}

    with pytest.raises(MetricBundleStorageError, match="corrupt or unreadable"):
        await load_bundle(sdk, "default/metric-bundle.deadbeef#bundle.json")


async def test_delete_by_ref_removes_only_that_fileset() -> None:
    sdk = _FakeSDK()
    bundle = _sample_bundle()
    ref1 = await store_bundle(sdk, "default", "my-metric", bundle)
    ref2 = await store_bundle(sdk, "default", "my-metric", bundle)

    await delete_bundle_by_ref(sdk, ref1)

    _, fileset1, _ = parse_bundle_ref(ref1)
    _, fileset2, _ = parse_bundle_ref(ref2)
    assert ("default", fileset1) not in sdk._store
    assert ("default", fileset2) in sdk._store
