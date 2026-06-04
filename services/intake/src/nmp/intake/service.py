# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Intake service implementation."""

import logging
from typing import ClassVar, List

from nmp.common.service import RouterConfig, Service
from nmp.intake.api.v2.experiments import endpoints as experiments
from nmp.intake.config import IntakeConfig
from nmp.intake.spans.api import annotations, evaluator_results, spans, traces
from nmp.intake.spans.clickhouse_client import ClickHouseSettings, ClickHouseSpanClient
from nmp.intake.spans.ingest import atif, chat_completions, otlp

logger = logging.getLogger(__name__)


class IntakeService(Service[IntakeConfig]):
    """Intake service for NeMo Platform."""

    dependencies: ClassVar[List[str]] = ["entities", "auth"]

    def __init__(self):
        """Initialize the intake service."""
        super().__init__(name="intake", module_name="nmp.intake")
        # The client is owned by the service lifecycle; it is absent before startup and after shutdown.
        self.clickhouse_client: ClickHouseSpanClient | None = None
        self._ready = False

    @property
    def title(self) -> str:
        return "Intake API"

    @property
    def description(self) -> str:
        return "Intake service for ingesting and reading spans, traces, annotations, and evaluator results"

    def get_routers(self) -> List[RouterConfig]:
        """Return routers for the intake service."""
        return [
            RouterConfig(spans.router, tag="Spans", description="ClickHouse-backed span read endpoints"),
            RouterConfig(traces.router, tag="Traces", description="ClickHouse-backed trace summary read endpoints"),
            RouterConfig(
                evaluator_results.router,
                tag="Evaluator Results",
                description="ClickHouse-backed evaluator_result endpoints",
            ),
            RouterConfig(
                annotations.router,
                tag="Annotations",
                description="Post-hoc annotation endpoints (feedback, labels, notes, metadata)",
            ),
            RouterConfig(
                experiments.router,
                tag="Experiments",
                description="Create, list, get, and delete Experiments and Experiment Groups",
            ),
            RouterConfig(otlp.router, tag="Ingest", description="OTLP/HTTP trace ingest endpoints"),
            RouterConfig(atif.router, tag="Ingest", description="ATIF trajectory ingest endpoints"),
            RouterConfig(
                chat_completions.router,
                tag="Ingest",
                description="OpenAI-compatible chat-completion ingest endpoint",
            ),
        ]

    async def on_startup(self) -> None:
        """Create the trace storage client without requiring ClickHouse to be online."""

        cfg = self.service_config or IntakeConfig()
        self.clickhouse_client = ClickHouseSpanClient(ClickHouseSettings.from_config(cfg))
        logger.warning(
            "ClickHouse schema setup was not run during Intake startup; "
            "trace endpoints will initialize ClickHouse on first use and return 503 until it is reachable",
            extra={
                "service": self.name,
                "clickhouse_url": cfg.clickhouse_config.url,
                "clickhouse_database": cfg.clickhouse_config.database,
            },
        )
        self._ready = True

    async def on_shutdown(self) -> None:
        """Close the service-owned ClickHouse client."""

        self._ready = False
        if self.clickhouse_client is not None:
            await self.clickhouse_client.close()
            self.clickhouse_client = None
        await super().on_shutdown()

    async def is_ready(self) -> bool:
        return self._ready
