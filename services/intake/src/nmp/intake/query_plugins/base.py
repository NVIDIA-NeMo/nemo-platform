# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base contract for query plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

from nmp.intake.query_plugins.context import QueryPluginContext
from pydantic import BaseModel


class QueryPlugin(ABC):
    """A registered, plugin-owned ClickHouse query exposed via the generic query-plugin API.

    Query plugins are stateless.
    Careful, raw SQL is allowed —  bind every value as a ``%(name)s`` parameter so 
    nothing is interpolated into the query string.
    """

    id: ClassVar[str]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def build_query(self, ctx: QueryPluginContext) -> tuple[str, dict[str, Any]]:
        """Return ``(clickhouse_sql, bound_params)`` for this plugin's scope."""

    @abstractmethod
    def parse(self, rows: list[dict[str, Any]]) -> BaseModel:
        """Map raw ClickHouse result rows to ``output_model``."""
