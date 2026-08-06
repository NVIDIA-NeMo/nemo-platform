# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Intake service implementation."""

import logging
from dataclasses import replace
from typing import ClassVar, List

from nmp.common.service import RouterConfig, Service
from nmp.intake.api.v2.experiments import endpoints as experiments
from nmp.intake.config import IntakeConfig, should_provision_local_clickhouse
from nmp.intake.local_clickhouse import (
    DockerUnavailableError,
    LocalClickHouseProvisioningError,
    reconcile_local_clickhouse,
)
from nmp.intake.spans.api import annotations, evaluator_results, sessions, spans, traces
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
        return "Intake service for ingesting and reading sessions, traces, spans, annotations, and evaluator results"

    def get_routers(self) -> List[RouterConfig]:
        """Return routers for the intake service."""
        return [
            RouterConfig(spans.router, tag="Spans", description="ClickHouse-backed span read endpoints"),
            RouterConfig(traces.router, tag="Traces", description="ClickHouse-backed trace summary read endpoints"),
            RouterConfig(sessions.router, tag="Sessions", description="ClickHouse-backed session detail endpoints"),
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
                description="Create, list, get, and delete Evaluations and Experiments",
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
        settings = ClickHouseSettings.from_config(cfg)
        if should_provision_local_clickhouse(cfg.clickhouse_config):
            try:
                local_url = await reconcile_local_clickhouse(
                    settings,
                    image=cfg.clickhouse_config.image,
                    data_dir=cfg.clickhouse_config.data_dir,
                )
                settings = replace(settings, url=local_url)
            except DockerUnavailableError as exc:
                logger.warning(
                    "Skipping local ClickHouse reconciliation: %s ClickHouse-backed endpoints will return 503 until "
                    "ClickHouse is reachable.",
                    exc,
                    extra={"service": self.name, "clickhouse_url": settings.url},
                )
            except LocalClickHouseProvisioningError as exc:
                logger.error(
                    "Local ClickHouse reconciliation failed: %s Intake will continue starting; ClickHouse-backed "
                    "endpoints will return 503 until ClickHouse is reachable.",
                    exc,
                    extra={"service": self.name, "clickhouse_url": settings.url},
                )

        self.clickhouse_client = ClickHouseSpanClient(settings)
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
