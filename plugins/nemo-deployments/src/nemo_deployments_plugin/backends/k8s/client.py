# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes client bootstrap for the deployments plugin.

Copied from the jobs service pattern; tagged for future extraction to a shared substrate lib.

Imports are centralized in ``_kubernetes_modules()`` rather than hoisted to module scope so
``registry`` can load without requiring the optional ``kubernetes`` package until a k8s
executor is actually constructed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kubernetes.client import ApiClient, AppsV1Api, BatchV1Api, CoreV1Api

logger = logging.getLogger(__name__)

_kubernetes_modules_cache: tuple[Any, Any] | None = None


def _kubernetes_modules() -> tuple[Any, Any]:
    """Return ``(kubernetes.client, kubernetes.config)``, importing on first use."""
    global _kubernetes_modules_cache
    if _kubernetes_modules_cache is None:
        from kubernetes import client, config

        _kubernetes_modules_cache = (client, config)
    return _kubernetes_modules_cache


def build_api_client(*, kubeconfig_path: str | None = None) -> ApiClient:
    """Create an ``ApiClient`` for the given kubeconfig (in-cluster when path is unset)."""
    client, config = _kubernetes_modules()
    configuration = client.Configuration()
    if kubeconfig_path:
        config.load_kube_config(config_file=kubeconfig_path, client_configuration=configuration)
    else:
        try:
            config.load_incluster_config(client_configuration=configuration)
        except config.ConfigException:
            config.load_kube_config(client_configuration=configuration)
    return client.ApiClient(configuration)


class KubernetesClients:
    """Lazy Kubernetes API clients with per-instance kubeconfig and request timeout."""

    def __init__(self, *, kubeconfig_path: str | None = None, request_timeout: int = 60) -> None:
        self._kubeconfig_path = kubeconfig_path
        self._request_timeout = request_timeout
        self._api_client: ApiClient | None = None
        self._core_v1: CoreV1Api | None = None
        self._apps_v1: AppsV1Api | None = None
        self._batch_v1: BatchV1Api | None = None

    @property
    def request_timeout(self) -> int:
        """Per-request timeout (seconds) for Kubernetes API calls in later phases."""
        return self._request_timeout

    def _api(self) -> ApiClient:
        if self._api_client is None:
            self._api_client = build_api_client(kubeconfig_path=self._kubeconfig_path)
            logger.debug(
                "Kubernetes ApiClient created (kubeconfig_path=%s, request_timeout=%s)",
                self._kubeconfig_path,
                self._request_timeout,
            )
        return self._api_client

    @property
    def core_v1(self) -> CoreV1Api:
        if self._core_v1 is None:
            client, _ = _kubernetes_modules()
            self._core_v1 = client.CoreV1Api(self._api())
        return self._core_v1

    @property
    def apps_v1(self) -> AppsV1Api:
        if self._apps_v1 is None:
            client, _ = _kubernetes_modules()
            self._apps_v1 = client.AppsV1Api(self._api())
        return self._apps_v1

    @property
    def batch_v1(self) -> BatchV1Api:
        if self._batch_v1 is None:
            client, _ = _kubernetes_modules()
            self._batch_v1 = client.BatchV1Api(self._api())
        return self._batch_v1

    def close(self) -> None:
        """Release the underlying ``ApiClient`` connection pool, if created.

        ``CoreV1Api`` / ``AppsV1Api`` / ``BatchV1Api`` share the same ``ApiClient`` instance;
        closing it invalidates the cached API wrappers (reset below).
        """
        if self._api_client is not None:
            self._api_client.close()
            self._api_client = None
            self._core_v1 = None
            self._apps_v1 = None
            self._batch_v1 = None
