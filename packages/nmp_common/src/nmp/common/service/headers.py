# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Header utilities for internal NeMo Platform service-to-service HTTP calls."""

from typing import Dict

from nmp.common.auth import NMP_ORIGIN_WORKSPACE_HEADER, build_service_principal_headers
from nmp.common.observability.otel import get_otel_headers


def build_downstream_service_headers(
    service_name: str,
    *,
    origin_workspace: str | None = None,
) -> Dict[str, str]:
    """Build the full set of headers for HTTP requests to downstream NeMo Platform services.

    This is used when constructing the SDK client for entity operations
    via DependencyProvider._get_entity_sdk_on_behalf_of().

    This should also be used when a service needs to manually forward headers to a NeMo Platform
    service via a raw HTTP client (i.e. not via the pre-configured NeMo Platform SDK). For example,
    Guardrails invokes IGW via Langchain, which internally makes the call via its own HTTP
    client. This function returns the headers that should be forwarded to IGW via that
    internal client.

    Args:
        service_name: The calling service's name (e.g. ``"guardrails"``).
        origin_workspace: Trusted workspace from the current route for delegated
            downstream requests.

    Returns:
        Header dictionary ready to merge into an outbound request.

    Example::

        headers = build_downstream_service_headers("guardrails")
        # headers == {
        #   "traceparent": "...",
        #   "X-NMP-Principal-Id": "service:guardrails",
        #   "X-NMP-Principal-On-Behalf-Of": "<user-id>",   # if user in context
        # }
    """
    headers = {**get_otel_headers(), **build_service_principal_headers(service_name)}
    if origin_workspace:
        headers[NMP_ORIGIN_WORKSPACE_HEADER] = origin_workspace
    return headers
