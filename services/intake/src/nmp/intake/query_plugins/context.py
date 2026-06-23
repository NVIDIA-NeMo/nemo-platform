# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Scope handed to a query plugin when it builds its ClickHouse query."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


def _identity_table(name: str) -> str:
    return name


@dataclass(frozen=True)
class QueryPluginContext:
    """Scope passed to :meth:`QueryPlugin.build_query`.

    Always carries ``workspace``; optional scope fields (``experiment_ids`` today) are populated by
    the endpoint per the plugin's needs. ``table`` resolves a bare table name to its fully-qualified
    ClickHouse name — the runner wires the span client's resolver; it defaults to identity so unit
    tests can assert on bare table names.
    """

    workspace: str
    experiment_ids: tuple[str, ...] = ()
    table: Callable[[str], str] = _identity_table

    def experiment_id_parameters(self) -> tuple[str, dict[str, str]]:
        """Return ``(placeholders_sql, params)`` for an ``experiment_id IN (...)`` clause.

        Ids are de-duplicated and each is bound as a ``%(experiment_id_N)s`` parameter, so values
        are never interpolated into SQL.
        """
        unique_ids = list(dict.fromkeys(self.experiment_ids))
        parameters = {f"experiment_id_{index}": experiment_id for index, experiment_id in enumerate(unique_ids)}
        placeholders = ", ".join(f"%({name})s" for name in parameters)
        return placeholders, parameters

    def base_parameters(self) -> dict[str, str]:
        """Workspace + experiment-id parameters every experiment-scoped query plugin binds."""
        _, experiment_parameters = self.experiment_id_parameters()
        return {"workspace": self.workspace, **experiment_parameters}
