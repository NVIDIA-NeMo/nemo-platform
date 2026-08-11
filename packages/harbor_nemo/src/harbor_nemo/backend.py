# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The NeMo registry backend: one host, four collaborators."""

from __future__ import annotations

from typing import override

from harbor.publisher.base import BasePublisher
from harbor.registry.backend import BaseRegistryBackend
from harbor.registry.client.base import BaseRegistryClient
from harbor.registry.task_resolver import BaseTaskResolver
from harbor.storage.base import BaseStorage

from harbor_nemo.client import NemoClient
from harbor_nemo.config import NemoConfig
from harbor_nemo.dataset_client import NemoDatasetClient
from harbor_nemo.publisher import NemoPublisher
from harbor_nemo.storage import NemoStorage
from harbor_nemo.task_resolver import NemoTaskResolver


class NemoRegistryBackend(BaseRegistryBackend):
    """Publishes to and reads from a NeMo Platform.

    Every collaborator is built once and memoized. That is the interface's requirement, and it
    is load bearing here for a second reason: all four share one ``NemoClient``, so a single
    HTTP connection pool serves a 50-wide ``publish_tasks`` instead of 50 pools.

    ``package_type`` is left as the inherited default, which probes the dataset client and
    then the task resolver. NeMo has no single endpoint that answers "is this a task or a
    taskset", so overriding it would mean making the same two requests with more code.
    """

    def __init__(self, config: NemoConfig | None = None) -> None:
        self._config = config or NemoConfig.from_env()
        self._client = NemoClient(self._config)
        self._storage_instance: NemoStorage | None = None
        self._publisher_instance: NemoPublisher | None = None
        self._dataset_client_instance: NemoDatasetClient | None = None
        self._task_resolver_instance: NemoTaskResolver | None = None

    @property
    def config(self) -> NemoConfig:
        return self._config

    def _nemo_storage(self) -> NemoStorage:
        """The concrete storage. ``storage()`` narrows to the interface for callers; the
        publisher and dataset client need the NeMo-specific helpers (``exists``,
        ``to_fileset_ref``), and must get *this* instance, not another one."""
        if self._storage_instance is None:
            self._storage_instance = NemoStorage(self._client, self._config)
        return self._storage_instance

    @override
    def storage(self) -> BaseStorage:
        return self._nemo_storage()

    @override
    def publisher(self) -> BasePublisher:
        if self._publisher_instance is None:
            # The publisher writes blobs where the resolver will read them: same fileset,
            # same host, because it is handed this backend's storage rather than opening its
            # own client.
            self._publisher_instance = NemoPublisher(
                self._client, self._config, self._nemo_storage(), self._nemo_resolver()
            )
        return self._publisher_instance

    @override
    def dataset_client(self) -> BaseRegistryClient:
        if self._dataset_client_instance is None:
            self._dataset_client_instance = NemoDatasetClient(
                self._client, self._config, self._nemo_storage()
            )
        return self._dataset_client_instance

    def _nemo_resolver(self) -> NemoTaskResolver:
        """The concrete resolver, for the same reason as ``_nemo_storage``: the publisher
        needs ``revision_digest_for_archive`` to pin a dataset's members, and it must be the
        same instance the download side resolves through."""
        if self._task_resolver_instance is None:
            self._task_resolver_instance = NemoTaskResolver(self._client, self._config)
        return self._task_resolver_instance

    @override
    def task_resolver(self) -> BaseTaskResolver:
        return self._nemo_resolver()

    async def aclose(self) -> None:
        """Release the shared HTTP client. The CLI is short lived and does not call this."""
        await self._client.aclose()
