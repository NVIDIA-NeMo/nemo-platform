# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NemoClient factory for task containers and services.

Builds :class:`~nemo_platform_plugin.client.client.NemoClient` /
:class:`~nemo_platform_plugin.client.client.AsyncNemoClient` from
environment variables (``NMP_BASE_URL``, ``NMP_PRINCIPAL``).

For user-facing / CLI usage, prefer ``NemoClient.from_config()`` which
reads ``~/.config/nmp/config.yaml`` and wires up OIDC token refresh.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from nemo_platform_plugin.client.client import AsyncNemoClient, NemoClient

logger = logging.getLogger(__name__)

_INTERNAL_REQUEST_HEADER = "X-NMP-Internal"
_NMP_PRINCIPAL_ENVVAR = "NMP_PRINCIPAL"


def _read_principal_from_env() -> dict[str, Any] | None:
    raw = os.environ.get(_NMP_PRINCIPAL_ENVVAR)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {_NMP_PRINCIPAL_ENVVAR}: {exc}") from exc
    if not isinstance(data, dict) or not data.get("id"):
        return None
    return data


def _build_headers(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> dict[str, str]:
    """Build X-NMP-* headers from env vars and explicit parameters."""
    headers: dict[str, str] = {}

    if internal:
        headers[_INTERNAL_REQUEST_HEADER] = "true"

    if as_service is not None:
        headers["X-NMP-Principal-Id"] = f"service:{as_service}"
    else:
        principal = _read_principal_from_env()
        if principal is not None:
            headers["X-NMP-Principal-Id"] = principal["id"]
            if principal.get("email"):
                headers["X-NMP-Principal-Email"] = principal["email"]
            if principal.get("groups"):
                headers["X-NMP-Principal-Groups"] = ",".join(principal["groups"])
            if principal.get("on_behalf_of"):
                headers["X-NMP-Principal-On-Behalf-Of"] = principal["on_behalf_of"]
                if principal.get("on_behalf_of_email"):
                    headers["X-NMP-Principal-On-Behalf-Of-Email"] = principal["on_behalf_of_email"]
                if principal.get("on_behalf_of_groups"):
                    headers["X-NMP-Principal-On-Behalf-Of-Groups"] = ",".join(principal["on_behalf_of_groups"])

    if on_behalf_of is not None:
        headers["X-NMP-Principal-On-Behalf-Of"] = on_behalf_of

    return headers


def _base_url() -> str:
    return os.environ.get("NMP_BASE_URL", "http://localhost:8080")


def get_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> NemoClient:
    """Build a sync NemoClient for the current service context.

    Reads ``NMP_BASE_URL`` (default ``http://localhost:8080``) and
    ``NMP_PRINCIPAL`` from the environment.
    """
    headers = _build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
    return NemoClient(base_url=_base_url(), default_headers=headers or None)


def get_async_nemo_client(
    *,
    as_service: str | None = None,
    internal: bool = False,
    on_behalf_of: str | None = None,
) -> AsyncNemoClient:
    """Build an async NemoClient for the current service context.

    Reads ``NMP_BASE_URL`` (default ``http://localhost:8080``) and
    ``NMP_PRINCIPAL`` from the environment.
    """
    headers = _build_headers(as_service=as_service, internal=internal, on_behalf_of=on_behalf_of)
    return AsyncNemoClient(base_url=_base_url(), default_headers=headers or None)
