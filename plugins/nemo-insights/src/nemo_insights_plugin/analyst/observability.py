# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry setup for analyst self-observability."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

from nemo_insights_plugin.client import LOOPBACK_HOSTS
from nemo_platform.config.config import Config
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from pydantic_ai.models.instrumented import InstrumentationSettings

ANALYST_OBSERVABILITY_ENV = "NEMO_INSIGHTS_ANALYST_OBSERVABILITY"
ANALYST_OBSERVABILITY_AGENT_NAME = "nemo-insights-analyst"
ANALYST_OBSERVABILITY_SERVICE_NAMESPACE = "nemo-insights"
OTLP_TRACES_PATH = "/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces"


@dataclass
class AnalystObservability:
    """Configured Pydantic AI instrumentation for one analyst run."""

    endpoint: str
    session_id: str
    instrumentation_settings: InstrumentationSettings
    tracer_provider: TracerProvider

    @property
    def metadata(self) -> dict[str, str]:
        """Metadata attached to the Pydantic AI agent run span."""
        return {
            "session.id": self.session_id,
            "gen_ai.conversation.id": self.session_id,
        }

    def shutdown(self) -> None:
        """Flush pending spans and stop the provider's processors."""
        self.tracer_provider.force_flush()
        self.tracer_provider.shutdown()


def build_intake_otlp_traces_endpoint(*, base_url: str, workspace: str) -> str:
    """Return Intake's workspace-scoped OTLP/HTTP traces endpoint."""
    return f"{base_url.rstrip('/')}{OTLP_TRACES_PATH.format(workspace=workspace)}"


def setup_analyst_observability(
    *,
    base_url: str,
    workspace: str,
    target_agent: str,
) -> AnalystObservability:
    """Configure native Pydantic AI OTel instrumentation for Intake export.

    This path is intended for insights dogfooding and is opt-in at the CLI
    layer, so it always sends the analyst's own spans to the platform Intake
    endpoint derived from the active ``--base-url`` and ``--workspace``.
    """
    endpoint = build_intake_otlp_traces_endpoint(base_url=base_url, workspace=workspace)
    session_id = f"{ANALYST_OBSERVABILITY_AGENT_NAME}-{uuid4()}"
    resource_attributes = _resource_attributes(
        workspace=workspace,
        target_agent=target_agent,
        session_id=session_id,
    )

    tracer_provider = TracerProvider(resource=Resource.create(resource_attributes))
    otlp_headers = _otlp_auth_headers(base_url)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=endpoint,
                headers=otlp_headers,
            )
        )
    )
    instrumentation_settings = InstrumentationSettings(
        tracer_provider=tracer_provider,
        include_content=True,
    )
    return AnalystObservability(
        endpoint=endpoint,
        session_id=session_id,
        instrumentation_settings=instrumentation_settings,
        tracer_provider=tracer_provider,
    )


def _otlp_auth_headers(base_url: str) -> dict[str, str] | None:
    """Return Bearer auth headers for remote Intake OTLP ingest, if available."""
    host = (urlparse(base_url).hostname or "").lower()
    config_path = Config.get_default_config_path()
    if host in LOOPBACK_HOSTS or not config_path.exists():
        return None

    config = Config.load(config_path, overrides={"base_url": base_url})
    user = config.resolve().user
    assert user is not None
    client_config = user.get_client_config()
    headers = client_config.get("default_headers")
    if not isinstance(headers, dict):
        return None
    return {str(k): str(v) for k, v in headers.items()}


def _resource_attributes(*, workspace: str, target_agent: str, session_id: str) -> dict[str, str]:
    return {
        "service.name": ANALYST_OBSERVABILITY_AGENT_NAME,
        "service.namespace": ANALYST_OBSERVABILITY_SERVICE_NAMESPACE,
        "gen_ai.agent.name": ANALYST_OBSERVABILITY_AGENT_NAME,
        "gen_ai.agent.id": ANALYST_OBSERVABILITY_AGENT_NAME,
        "project.name": ANALYST_OBSERVABILITY_AGENT_NAME,
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        "nemo.insights.workspace": workspace,
        "nemo.insights.target_agent": target_agent,
    }
