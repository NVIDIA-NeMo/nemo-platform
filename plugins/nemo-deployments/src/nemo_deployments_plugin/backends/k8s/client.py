# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes client bootstrap for the deployments plugin.

Copied from the jobs service pattern; tagged for future extraction to a shared substrate lib.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kubernetes import client

logger = logging.getLogger(__name__)


def build_api_client(*, kubeconfig_path: str | None = None) -> client.ApiClient:
    """Create an ``ApiClient`` for the given kubeconfig (in-cluster when path is unset)."""
    from kubernetes import client, config

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
        self._api_client: client.ApiClient | None = None
        self._core_v1: client.CoreV1Api | None = None
        self._apps_v1: client.AppsV1Api | None = None
        self._batch_v1: client.BatchV1Api | None = None

    @property
    def request_timeout(self) -> int:
        """Per-request timeout (seconds) for Kubernetes API calls in later phases."""
        return self._request_timeout

    def _api(self) -> client.ApiClient:
        if self._api_client is None:
            self._api_client = build_api_client(kubeconfig_path=self._kubeconfig_path)
            logger.debug(
                "Kubernetes ApiClient created (kubeconfig_path=%s, request_timeout=%s)",
                self._kubeconfig_path,
                self._request_timeout,
            )
        return self._api_client

    @property
    def core_v1(self) -> client.CoreV1Api:
        if self._core_v1 is None:
            from kubernetes import client

            self._core_v1 = client.CoreV1Api(self._api())
        return self._core_v1

    @property
    def apps_v1(self) -> client.AppsV1Api:
        if self._apps_v1 is None:
            from kubernetes import client

            self._apps_v1 = client.AppsV1Api(self._api())
        return self._apps_v1

    @property
    def batch_v1(self) -> client.BatchV1Api:
        if self._batch_v1 is None:
            from kubernetes import client

            self._batch_v1 = client.BatchV1Api(self._api())
        return self._batch_v1
