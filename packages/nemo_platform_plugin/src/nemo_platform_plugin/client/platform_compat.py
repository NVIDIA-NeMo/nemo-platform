# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""SDK-level backward compat for BaseNemoClient.

Adds attributes and methods that the old Stainless NeMoPlatform exposed
(``_client``, ``default_headers``, ``close``, ``copy``, and ``__getattr__``
for plugin SDK discovery) so that code written against the Stainless SDK
continues to work after the spine flip to NemoClient.

Temporary: removed after all consumers are migrated.
"""

from __future__ import annotations

from typing import Any


class PlatformCompat:
    """Mixin adding old-SDK-level attributes to BaseNemoClient."""

    @property
    def _client(self) -> Any:
        """Underlying httpx client (old SDK exposed this as ``_client``)."""
        return self._http

    @property
    def default_headers(self) -> dict[str, str]:
        """Default headers dict (old SDK exposed this as ``default_headers``)."""
        return self._default_headers or {}

    def close(self) -> None:
        """Close the underlying HTTP transport."""
        self._http.close()

    def copy(self, **kwargs: Any) -> Any:
        """Alias for with_options (old SDK's copy was with_options)."""
        return self.with_options(**kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to plugin SDK discovery.

        Mirrors the enhanced NeMoPlatform.__getattr__: discovers plugin SDK
        resources via entry points and instantiates them with self as the
        platform.  This handles sdk.anonymizer, sdk.customization, and any
        other plugin-level resource not covered by convenience properties.
        """
        # __getattr__ is only called when normal attribute lookup fails.
        # Convenience properties (.files, .models, .workspaces, etc.) are
        # real properties and take precedence.
        from nemo_platform_plugin.client.client import AsyncNemoClient
        from nemo_platform_plugin.discovery import discover_sdk

        plugins = discover_sdk()
        if name not in plugins:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        if isinstance(self, AsyncNemoClient):
            resource_cls = getattr(plugins[name], "async_resource", None)
        else:
            resource_cls = getattr(plugins[name], "sync_resource", None)
        if resource_cls is None:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute {name!r}")

        instance = resource_cls(self)
        self.__dict__[name] = instance
        return instance
