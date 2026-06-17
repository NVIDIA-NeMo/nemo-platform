# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from nemo_evaluator.api.schemas import MetricInline
from nemo_evaluator.entities import MetricBundleEntity
from nemo_evaluator.jobs.evaluate import EvaluateInputSpec, EvaluateSpec
from nemo_evaluator.metric_refs import (
    MetricRef,
    parse_metric_ref,
    resolve_metric_specs,
)
from nemo_evaluator.metric_storage import store_bundle
from nemo_evaluator.shared.metric_bundles.bundles import bundle_metric
from nemo_evaluator.shared.metric_bundles.cloudpickle import CloudpickleMetricBundlePackager
from nemo_evaluator_sdk.metrics.exact_match import ExactMatchMetric
from nemo_platform_plugin.entities import EntityNotFoundError
from pydantic import ValidationError

# ---- in-memory fakes (mirror the storage round-trip) -----------------------


class _FakeFile:
    def __init__(self, file_ref: str) -> None:
        self.file_ref = file_ref


class _FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeFilesets:
    def __init__(self, store) -> None:
        self._store = store

    async def create(self, *, name, workspace, description=None, exist_ok=False):
        self._store.setdefault((workspace, name), {})
        return object()

    async def delete(self, name, *, workspace=None):
        self._store.pop((workspace, name), None)
        return object()


class _FakeFiles:
    def __init__(self, store) -> None:
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


class _FakeEntityClient:
    def __init__(self) -> None:
        self.entities: dict[tuple[str, str], MetricBundleEntity] = {}

    async def get(self, entity_cls, *, workspace, name):
        try:
            return self.entities[(workspace, name)]
        except KeyError:
            raise EntityNotFoundError(f"{workspace}/{name} not found")


def _bundle():
    metric = ExactMatchMetric(reference="{{item.expected}}", candidate="{{item.output}}")
    return bundle_metric(metric, CloudpickleMetricBundlePackager())


def _metric_inline() -> MetricInline:
    """An inline metric as carried on the wire (MetricInline DTO)."""
    return MetricInline.model_validate_json(_bundle().model_dump_json())


async def _stored(sdk: _FakeSDK, entity_client: _FakeEntityClient, workspace: str, name: str):
    bundle = _bundle()
    ref = await store_bundle(sdk, workspace, name, bundle)
    entity_client.entities[(workspace, name)] = MetricBundleEntity(
        name=name,
        workspace=workspace,
        metric_type=bundle.metric_type,
        outputs=bundle.outputs,
        payload_kind=bundle.payload.kind,
        payload_digest=bundle.payload.digest,
        bundle_ref=ref,
    )
    return bundle


# ---- ref parsing -----------------------------------------------------------


def test_parse_metric_ref_qualified() -> None:
    assert parse_metric_ref("ws/my-metric", "default") == ("ws", "my-metric")


def test_parse_metric_ref_bare_name_uses_default_workspace() -> None:
    assert parse_metric_ref("my-metric", "default") == ("default", "my-metric")


@pytest.mark.parametrize("ref", ["", "ws/", "/name", "ws/a/b", "bad name"])
def test_metric_ref_field_rejects_malformed(ref: str) -> None:
    # Malformed refs are rejected by the MetricRef field pattern at validation time.
    with pytest.raises(ValidationError):
        MetricRef(root=ref)


# ---- resolution ------------------------------------------------------------


async def test_resolve_converts_inline_metric_to_runtime_bundle() -> None:
    inline = _metric_inline()
    result = await resolve_metric_specs([inline], workspace="default", entity_client=None, async_sdk=None)
    assert len(result) == 1
    assert result[0].metric_type == inline.metric_type
    assert result[0].payload.digest == inline.payload.digest


async def test_resolve_loads_referenced_bundle() -> None:
    sdk = _FakeSDK()
    entity_client = _FakeEntityClient()
    stored = await _stored(sdk, entity_client, "default", "exact")

    result = await resolve_metric_specs(
        [MetricRef(root="default/exact")],
        workspace="default",
        entity_client=entity_client,
        async_sdk=sdk,
    )

    assert len(result) == 1
    assert result[0].payload.digest == stored.payload.digest


async def test_resolve_mixes_refs_and_inline_preserving_order() -> None:
    sdk = _FakeSDK()
    entity_client = _FakeEntityClient()
    await _stored(sdk, entity_client, "default", "exact")
    inline = _metric_inline()

    result = await resolve_metric_specs(
        [MetricRef(root="exact"), inline],
        workspace="default",
        entity_client=entity_client,
        async_sdk=sdk,
    )

    assert len(result) == 2
    assert result[1].payload.digest == inline.payload.digest


async def test_resolve_ref_without_sdk_raises() -> None:
    with pytest.raises(ValueError, match="require a platform connection"):
        await resolve_metric_specs(
            [MetricRef(root="default/exact")],
            workspace="default",
            entity_client=_FakeEntityClient(),
            async_sdk=None,
        )


async def test_resolve_missing_metric_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="not found"):
        await resolve_metric_specs(
            [MetricRef(root="default/no-such-metric")],
            workspace="default",
            entity_client=_FakeEntityClient(),
            async_sdk=_FakeSDK(),
        )


async def test_resolve_ref_without_entity_client_raises() -> None:
    with pytest.raises(ValueError, match="require a platform connection"):
        await resolve_metric_specs(
            [MetricRef(root="default/exact")],
            workspace="default",
            entity_client=None,
            async_sdk=_FakeSDK(),
        )


# ---- spec-level union behavior ---------------------------------------------


def test_input_spec_accepts_ref_and_inline() -> None:
    spec = EvaluateInputSpec(
        metrics=["default/stored-metric", _metric_inline()],
        dataset=[{"expected": "a", "output": "a"}],
    )
    assert isinstance(spec.metrics[0], MetricRef)
    assert spec.metrics[0].root == "default/stored-metric"


def test_canonical_spec_rejects_unresolved_ref() -> None:
    with pytest.raises(ValidationError):
        EvaluateSpec(
            metrics=["default/stored-metric"],
            dataset=[{"expected": "a", "output": "a"}],
        )
