# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK resources for managing stored metrics (``client.evaluator.metrics``).

These resources package a runtime metric into a :class:`MetricInline` wire DTO and
call the evaluator service's ``/metrics`` create/get/list/delete API (metrics are
immutable). The service owns the payload's Files storage, so the SDK only ever
sends/receives the metric and its metadata.
"""

from __future__ import annotations

from urllib.parse import quote

from nemo_evaluator.api.schemas import Metric, MetricInline
from nemo_evaluator.sdk import http_utils
from nemo_evaluator.shared.metric_bundles.bundles import (
    MetricBundle,
    MetricBundlePackager,
    bundle_metric,
)
from nemo_evaluator.shared.metric_bundles.defaults import resolve_default_metric_bundle_packager
from nemo_evaluator_sdk.metrics.protocol import Metric as RuntimeMetric
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform
from nemo_platform_plugin.schema import Page


def _metric_inline(
    metric: RuntimeMetric | MetricBundle,
    metric_bundle_packager: MetricBundlePackager | None,
) -> MetricInline:
    """Package a runtime metric (or accept a pre-built bundle) as the wire DTO."""
    if isinstance(metric, MetricBundle):
        bundle = metric
    else:
        packager = resolve_default_metric_bundle_packager(
            metric, metric_bundle_packager, allow_cloudpickle_fallback=False, action="Storing"
        )
        bundle = bundle_metric(metric, packager)
    # JSON round-trip keeps the base64 payload encoding consistent with the runtime model.
    return MetricInline.model_validate_json(bundle.model_dump_json())


class EvaluatorMetricsResource:
    """Sync resource mounted as ``client.evaluator.metrics``."""

    def __init__(self, platform: NeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/metrics", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform,
            f"/v2/workspaces/{{workspace}}/metrics/{quote(name, safe='')}",
            workspace,
        )

    def create(
        self,
        name: str,
        *,
        metric: RuntimeMetric | MetricBundle,
        metric_bundle_packager: MetricBundlePackager | None = None,
        project: str | None = None,
        workspace: str | None = None,
    ) -> Metric:
        """Store a new metric (addressed by workspace/name), packaging a runtime metric when needed."""
        body = _metric_inline(metric, metric_bundle_packager)
        response = self._http_client.post(
            self._item_url(name, workspace),
            json=body.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Metric.model_validate(response.json())

    def retrieve(self, name: str, *, workspace: str | None = None) -> Metric:
        """Get a stored metric by name."""
        response = self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Metric.model_validate(response.json())

    def list(self, *, workspace: str | None = None, page: int = 1, page_size: int = 100) -> Page[Metric]:
        """List stored metrics in a workspace."""
        response = self._http_client.get(
            self._collection_url(workspace),
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Metric].model_validate(response.json())

    def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored metric and its backing bundle."""
        response = self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()


class AsyncEvaluatorMetricsResource:
    """Async resource mounted as ``client.evaluator.metrics``."""

    def __init__(self, platform: AsyncNeMoPlatform) -> None:
        self._platform = platform
        self._http_client = platform._client

    def _headers(self) -> dict[str, str]:
        return http_utils.platform_default_headers(self._platform)

    def _collection_url(self, workspace: str | None) -> str:
        return http_utils.url(self._platform, "/v2/workspaces/{workspace}/metrics", workspace)

    def _item_url(self, name: str, workspace: str | None) -> str:
        return http_utils.url(
            self._platform,
            f"/v2/workspaces/{{workspace}}/metrics/{quote(name, safe='')}",
            workspace,
        )

    async def create(
        self,
        name: str,
        *,
        metric: RuntimeMetric | MetricBundle,
        metric_bundle_packager: MetricBundlePackager | None = None,
        project: str | None = None,
        workspace: str | None = None,
    ) -> Metric:
        """Store a new metric (addressed by workspace/name), packaging a runtime metric when needed."""
        body = _metric_inline(metric, metric_bundle_packager)
        response = await self._http_client.post(
            self._item_url(name, workspace),
            json=body.model_dump(mode="json"),
            params={"project": project} if project is not None else None,
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Metric.model_validate(response.json())

    async def retrieve(self, name: str, *, workspace: str | None = None) -> Metric:
        """Get a stored metric by name."""
        response = await self._http_client.get(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
        return Metric.model_validate(response.json())

    async def list(self, *, workspace: str | None = None, page: int = 1, page_size: int = 100) -> Page[Metric]:
        """List stored metrics in a workspace."""
        response = await self._http_client.get(
            self._collection_url(workspace),
            params={"page": page, "page_size": page_size},
            headers=self._headers(),
            timeout=self._platform.timeout,
        )
        response.raise_for_status()
        return Page[Metric].model_validate(response.json())

    async def delete(self, name: str, *, workspace: str | None = None) -> None:
        """Delete a stored metric and its backing bundle."""
        response = await self._http_client.delete(
            self._item_url(name, workspace), headers=self._headers(), timeout=self._platform.timeout
        )
        response.raise_for_status()
