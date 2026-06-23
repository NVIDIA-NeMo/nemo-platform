# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The query-plugin manifest — the backend half of the Studio plugin system.

Platform code loads deployed plugins from:

1. ``query_plugins/custom/registry_local.py`` (gitignored local dev manifest), and
2. modules listed in ``NEMO_QUERY_PLUGINS_MODULES`` (comma-separated import paths at image build).

Plugin implementations belong in a local ``custom/*.py`` module or an org wheel — not in this repo.
See ``query_plugins/custom/README.md``.
"""

from __future__ import annotations

import importlib
import logging
import os

from nmp.intake.query_plugins.base import QueryPlugin

logger = logging.getLogger(__name__)


def _load_local_plugins() -> list[QueryPlugin]:
    try:
        from nmp.intake.query_plugins.custom import registry_local
    except ImportError:
        return []
    plugins = getattr(registry_local, "QUERY_PLUGINS", None)
    if plugins is None:
        logger.warning("registry_local.py exists but does not define QUERY_PLUGINS")
        return []
    return list(plugins)


def _load_env_plugins() -> list[QueryPlugin]:
    plugins: list[QueryPlugin] = []
    for module_path in os.environ.get("NEMO_QUERY_PLUGINS_MODULES", "").split(","):
        module_path = module_path.strip()
        if not module_path:
            continue
        module = importlib.import_module(module_path)
        module_plugins = getattr(module, "QUERY_PLUGINS", None)
        if module_plugins is None:
            logger.warning("%s does not define QUERY_PLUGINS", module_path)
            continue
        plugins.extend(module_plugins)
    return plugins


def _merge_plugins(*sources: list[QueryPlugin]) -> list[QueryPlugin]:
    merged: list[QueryPlugin] = []
    seen: set[str] = set()
    for plugins in sources:
        for plugin in plugins:
            if plugin.id in seen:
                logger.warning("Duplicate query plugin id %r; keeping first registration", plugin.id)
                continue
            seen.add(plugin.id)
            merged.append(plugin)
    return merged


QUERY_PLUGINS: list[QueryPlugin] = _merge_plugins(_load_local_plugins(), _load_env_plugins())

_BY_ID: dict[str, QueryPlugin] = {plugin.id: plugin for plugin in QUERY_PLUGINS}


def get_query_plugin(query_plugin_id: str) -> QueryPlugin | None:
    """Return the registered query plugin with this id, or ``None`` if not deployed."""
    return _BY_ID.get(query_plugin_id)


def query_plugin_ids() -> list[str]:
    """Ids of every deployed query plugin (for the Studio availability manifest)."""
    return [plugin.id for plugin in QUERY_PLUGINS]
