# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Observability facade: settings, header context, and the ``initialize_obs`` coordinator.

Sub-modules house the heavy lifting:

* ``structured_logging``  -- structured logging, log filters, OTLP log export
* ``tracing``  -- OTel resource, tracing/metrics init, instrumentations
* ``middleware`` -- ``RequestLoggingMiddleware``

This module re-exports their public symbols via ``__getattr__`` so
existing ``from nmp.common.observability.otel import …`` paths keep
working.
"""

from __future__ import annotations

import os
from typing import Literal

# Header propagation lives in nemo_platform_plugin.otel_headers so plugins can
# import it without pulling in the full opentelemetry SDK. Service-side
# callers keep using `nmp.common.observability.otel` via these re-exports.
from nemo_platform_plugin.otel_headers import (
    INTERNAL_REQUEST_HEADER as INTERNAL_REQUEST_HEADER,
)
from nemo_platform_plugin.otel_headers import (
    MARK_INTERNAL_REQUEST_HEADERS as MARK_INTERNAL_REQUEST_HEADERS,
)
from nemo_platform_plugin.otel_headers import (
    get_otel_headers as get_otel_headers,
)
from nemo_platform_plugin.otel_headers import (
    otel_headers_context as otel_headers_context,
)
from nemo_platform_plugin.otel_headers import (
    scoped_otel_headers as scoped_otel_headers,
)
from nemo_platform_plugin.otel_headers import (
    set_otel_headers as set_otel_headers,
)
from pydantic_settings import BaseSettings


def _get_env_bool(var_name: str, default: bool = False) -> bool:
    val = os.getenv(var_name)
    if val is None:
        return default
    return val.lower() in ("1", "true")


class OTELSettings(BaseSettings):
    """
    OpenTelemetry configuration settings represented as a Pydantic model.

    See: https://opentelemetry.io/docs/specs/otel/configuration/sdk-environment-variables/
    """

    otel_sdk_disabled: bool = False
    otel_exporter_otlp_endpoint: str | None = None
    otel_exporter_otlp_insecure: bool = False
    otel_metrics_exporter: str = "none"
    otel_traces_exporter: str = "none"
    otel_logs_exporter: str = "none"
    otel_exporter_otlp_traces_endpoint: str | None = None
    otel_exporter_otlp_metrics_endpoint: str | None = None
    otel_exporter_otlp_logs_endpoint: str | None = None

    otel_nmp_include_auth_context: bool = True
    log_level: str = "INFO"
    extra_log_config: str = ""

    log_format: Literal["json", "plain"] = "plain"
    log_internal_requests: bool = False

    @property
    def otel_exporter_otlp_traces_insecure(self) -> bool:
        return self.otel_exporter_otlp_insecure or _get_env_bool("OTEL_EXPORTER_OTLP_TRACES_INSECURE")

    @property
    def otel_exporter_otlp_metrics_insecure(self) -> bool:
        return self.otel_exporter_otlp_insecure or _get_env_bool("OTEL_EXPORTER_OTLP_METRICS_INSECURE")

    @property
    def otel_exporter_otlp_logs_insecure(self) -> bool:
        return self.otel_exporter_otlp_insecure or _get_env_bool("OTEL_EXPORTER_OTLP_LOGS_INSECURE")


settings = OTELSettings()

_obs_initialized: bool = False


def initialize_obs(resource_attributes: dict[str, str] | None = None):
    """
    Entrypoint for initializing OpenTelemetry observability for this application.

    For FastAPI applications, this should be called during application lifespan initialization.
    Safe to call multiple times -- subsequent calls are no-ops.

    Args:
        resource_attributes: Optional attributes to attach to the OTEL resource so they
            appear on every span and metric (e.g. {"nmp.platform.platform_version": "26.2.0"}).
    """
    global _obs_initialized
    if _obs_initialized:
        return
    _obs_initialized = True

    from .tracing import create_otel_resource, initialize_metrics, initialize_tracing

    from .structured_logging import initialize_logging  # isort: skip

    resource = create_otel_resource(attributes=resource_attributes)
    if not settings.otel_sdk_disabled:
        initialize_tracing(resource)
        initialize_metrics(resource)
    initialize_logging(resource)


# ---------------------------------------------------------------------------
# Backward-compatible re-exports
#
# Symbols that moved to sub-modules are re-exported here via __getattr__
# so that existing ``from nmp.common.observability.otel import X`` paths
# keep working without triggering circular-import issues at module-init
# time.
# ---------------------------------------------------------------------------

_REEXPORT_MAP: dict[str, tuple[str, str]] = {
    "DiscardInternalRequests": (".structured_logging", "DiscardInternalRequests"),
    "DiscardSensitiveMessages": (".structured_logging", "DiscardSensitiveMessages"),
    "apply_extra_log_config": (".structured_logging", "apply_extra_log_config"),
    "clear_loggers": (".structured_logging", "clear_loggers"),
    "create_otel_log_processor": (".structured_logging", "create_otel_log_processor"),
    "initialize_logging": (".structured_logging", "initialize_logging"),
    "quiet_loggers": (".structured_logging", "quiet_loggers"),
    "RequestLoggingMiddleware": (".middleware", "RequestLoggingMiddleware"),
    "create_otel_resource": (".tracing", "create_otel_resource"),
    "initialize_metrics": (".tracing", "initialize_metrics"),
    "initialize_tracing": (".tracing", "initialize_tracing"),
    "setup_fastapi_instrumentations": (".tracing", "setup_fastapi_instrumentations"),
    "setup_global_instrumentations": (".tracing", "setup_global_instrumentations"),
}


def __getattr__(name: str):
    if name in _REEXPORT_MAP:
        module_path, attr = _REEXPORT_MAP[name]
        import importlib

        mod = importlib.import_module(module_path, __package__)
        value = getattr(mod, attr)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
