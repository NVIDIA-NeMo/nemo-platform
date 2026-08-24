# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Run-time dependencies shared by the analyst agent and its read methods.

The CLI builds one :class:`AnalystDeps` for each run. The Nooa agent keeps it
hidden from generated code and injects it into every scoped backend method.
Keeping it in its own module avoids an import cycle between the agent and the
read-method implementations.
"""

from dataclasses import dataclass
from datetime import datetime

from nemo_insights_plugin.analyst.analyst_backend import AnalystBackend
from nemo_platform_plugin.trace_provider import TraceProvider


@dataclass
class AnalystDeps:
    """Per-run configuration injected into every analyst read method.

    Trace tools use a shared :class:`TraceProvider`; Insight tools use the
    separate :class:`AnalystBackend`. Both are built once by the caller and
    injected here, so tools do not own their clients' lifecycles.

    Attributes:
        agent: Agent under test. Used as the default ``agent_name`` filter for
            span/insight tools.
        workspace: NMP workspace the analyst operates in.
        base_url: Base URL of the running NMP instance (run metadata; tools go
            through ``backend``).
        insights_output: When set, the backend also persists insights to this
            local YAML file, mirroring the rows the platform stored (run
            metadata).
        backend: Shared Insight listing and persistence backend.
        trace_provider: Shared read-only trace provider.
        since: Optional lower bound for scheduled incremental analysis. Trace
            reads enforce this even if the model omits a time filter.
        max_results: Hard ceiling on items any single fetch may pull across
            pages. A fetch's ``limit`` is clamped to this so a wide filter
            can't flood the model's context; the analyst paginates or narrows
            its filter to see more.
    """

    agent: str = ""
    workspace: str = "default"
    base_url: str | None = None
    insights_output: str | None = None
    backend: AnalystBackend | None = None
    trace_provider: TraceProvider | None = None
    since: datetime | None = None
    evaluation_id: str | None = None  # Intake evaluation scope configured on the provider
    max_results: int = 200
