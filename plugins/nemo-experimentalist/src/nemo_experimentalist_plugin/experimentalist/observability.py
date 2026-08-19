# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Nooa OpenTelemetry setup for Experimentalist self-observability."""

from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import uuid4

from nemo_insights_plugin.client import LOOPBACK_HOSTS
from nemo_platform.config.config import Config
from nooa.tracing import enable_tracing, exporters, flush_traces, set_session

EXPERIMENTALIST_OBSERVABILITY_ENV = "NEMO_EXPERIMENTALIST_OBSERVABILITY"
EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME = "Experimentalist"
EXPERIMENTALIST_OBSERVABILITY_SERVICE_NAMESPACE = "nemo-experimentalist"
OTLP_TRACES_PATH = "/apis/intake/v2/workspaces/{workspace}/ingest/otlp/v1/traces"


@dataclass
class ExperimentalistObservability:
    """Configured Nooa instrumentation for one Experimentalist run."""

    endpoint: str
    session_id: str

    def shutdown(self) -> None:
        """Flush this process's pending spans without disabling global tracing."""
        flush_traces()


def build_intake_otlp_traces_endpoint(*, base_url: str, workspace: str) -> str:
    """Return Intake's workspace-scoped OTLP/HTTP traces endpoint."""
    parsed = urlparse(base_url)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme != "https" and not (scheme == "http" and host in LOOPBACK_HOSTS):
        raise ValueError(
            f"Experimentalist observability endpoint must use HTTPS (got {base_url!r}). "
            "HTTP is only allowed for loopback addresses."
        )
    return f"{base_url.rstrip('/')}{OTLP_TRACES_PATH.format(workspace=workspace)}"


def setup_experimentalist_observability(
    *,
    base_url: str,
    workspace: str,
    target_agent: str,
) -> ExperimentalistObservability:
    """Configure native Nooa OTel instrumentation for Intake export."""
    endpoint = build_intake_otlp_traces_endpoint(base_url=base_url, workspace=workspace)
    session_id = f"{EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME}-{uuid4()}"
    resource_attributes = _resource_attributes(
        workspace=workspace,
        target_agent=target_agent,
        session_id=session_id,
    )

    otlp_headers = _otlp_auth_headers(base_url)
    enable_tracing(
        exporters=[exporters.otlp(endpoint=endpoint, headers=otlp_headers)],
        extra_resource_attrs=resource_attributes,
    )
    set_session(session_id)
    return ExperimentalistObservability(endpoint=endpoint, session_id=session_id)


def _otlp_auth_headers(base_url: str) -> dict[str, str] | None:
    """Return Bearer auth headers for remote Intake OTLP ingest, if available."""
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").lower()
    config_path = Config.get_default_config_path()
    if parsed.scheme.lower() != "https" or host in LOOPBACK_HOSTS or not config_path.exists():
        return None

    config = Config.load(config_path, overrides={"base_url": base_url})
    user = config.resolve().user
    assert user is not None
    client_config = user.get_client_config()
    headers = client_config.get("default_headers")
    if not isinstance(headers, dict):
        return None
    return {str(key): str(value) for key, value in headers.items()}


def _resource_attributes(*, workspace: str, target_agent: str, session_id: str) -> dict[str, str]:
    return {
        "service.name": EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME,
        "service.namespace": EXPERIMENTALIST_OBSERVABILITY_SERVICE_NAMESPACE,
        "gen_ai.agent.name": EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME,
        "gen_ai.agent.id": EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME,
        "project.name": EXPERIMENTALIST_OBSERVABILITY_AGENT_NAME,
        "session.id": session_id,
        "gen_ai.conversation.id": session_id,
        "nemo.experimentalist.workspace": workspace,
        "nemo.experimentalist.target_agent": target_agent,
    }
