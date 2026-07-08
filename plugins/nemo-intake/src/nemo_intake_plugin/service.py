# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Intake service implementation."""

import logging
from typing import ClassVar, Self

from nemo_platform_plugin.service import NemoService, RouterSpec

from nemo_intake_plugin.api.v2.experiments import endpoints as experiments
from nemo_intake_plugin.authz import apply_intake_authz
from nemo_intake_plugin.config import IntakeConfig, deprecated_intake_env_vars
from nemo_intake_plugin.spans.api import annotations, evaluator_results, spans, traces
from nemo_intake_plugin.spans.clickhouse_client import (
    ClickHouseSettings,
    ClickHouseSpanClient,
    get_intake_runtime,
)
from nemo_intake_plugin.spans.ingest import atif, chat_completions, otlp

logger = logging.getLogger(__name__)


class IntakeService(NemoService):
    """Intake service for NeMo Platform."""

    name: ClassVar[str] = "intake"
    description: ClassVar[str] = (
        "Intake service for ingesting and reading spans, traces, annotations, and evaluator results"
    )
    dependencies: ClassVar[list[str]] = ["entities", "auth"]

    def __init__(self) -> None:
        """Initialize the intake service."""
        # The client is owned by the service lifecycle; it is absent before startup and after shutdown.
        self.clickhouse_client: ClickHouseSpanClient | None = None
        self.service_config: IntakeConfig | None = None
        self._ready = False

    def with_config(self, config: IntakeConfig) -> Self:
        """Inject Intake config for tests."""

        self.service_config = config
        return self

    def get_routers(self) -> list[RouterSpec]:
        """Return routers for the intake service."""
        for router in (
            spans.router,
            traces.router,
            evaluator_results.router,
            annotations.router,
            experiments.router,
            otlp.router,
            atif.router,
            chat_completions.router,
        ):
            apply_intake_authz(router)

        return [
            RouterSpec(spans.router, tag="Spans", description="ClickHouse-backed span read endpoints"),
            RouterSpec(traces.router, tag="Traces", description="ClickHouse-backed trace summary read endpoints"),
            RouterSpec(
                evaluator_results.router,
                tag="Evaluator Results",
                description="ClickHouse-backed evaluator_result endpoints",
            ),
            RouterSpec(
                annotations.router,
                tag="Annotations",
                description="Post-hoc annotation endpoints (feedback, labels, notes, metadata)",
            ),
            RouterSpec(
                experiments.router,
                tag="Experiments",
                description="Create, list, get, and delete Experiments and Experiment Groups",
            ),
            RouterSpec(otlp.router, tag="Ingest", description="OTLP/HTTP trace ingest endpoints"),
            RouterSpec(atif.router, tag="Ingest", description="ATIF trajectory ingest endpoints"),
            RouterSpec(
                chat_completions.router,
                tag="Ingest",
                description="OpenAI-compatible chat-completion ingest endpoint",
            ),
        ]

    async def on_startup(self) -> None:
        """Create the trace storage client without requiring ClickHouse to be online."""

        deprecated_vars = deprecated_intake_env_vars()
        if deprecated_vars:
            logger.warning(
                "Deprecated NMP_INTAKE_* environment variables are set; use NEMO_INTAKE_* instead. "
                "The NMP_INTAKE_* aliases will be removed in a later release. "
                "Deprecated variables: %s",
                ", ".join(deprecated_vars),
                extra={"service": self.name, "deprecated_env_vars": deprecated_vars},
            )

        cfg = self.service_config or IntakeConfig.get()
        self.service_config = cfg
        self.clickhouse_client = ClickHouseSpanClient(ClickHouseSettings.from_config(cfg))
        get_intake_runtime().configure(self.clickhouse_client, cfg)
        logger.warning(
            "ClickHouse schema setup was not run during Intake startup; "
            "trace endpoints will initialize ClickHouse on first use and return 503 until it is reachable. "
            "For local development, start ClickHouse with plugins/nemo-intake/scripts/spans/run_clickhouse.sh; "
            "see plugins/nemo-intake/README.md#local-development.",
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
            client = self.clickhouse_client
            try:
                await client.close()
            finally:
                get_intake_runtime().clear(client)
                self.clickhouse_client = None
        await super().on_shutdown()

    async def is_ready(self) -> bool:
        return self._ready
