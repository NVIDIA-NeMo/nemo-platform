# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Live upstream probes for stored BYOK credentials."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast

import httpx

from scaled_evals.api import crypto
from scaled_evals.api.schemas.credentials import CredentialProvider, PayloadKind
from scaled_evals.api.settings import settings


@dataclass(frozen=True)
class CredentialVerificationResult:
    verified: bool | None
    reason: str


class CredentialVerificationFailed(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class CredentialVerificationUnavailable(Exception):
    pass


HeaderStyle = Literal["bearer", "anthropic"]


@dataclass(frozen=True)
class _Probe:
    url: str | None
    header_style: HeaderStyle


def _probe_for(provider: CredentialProvider) -> _Probe | None:
    if provider == "openai":
        return _Probe(settings.credential_verify_openai_models_url, "bearer")
    if provider == "anthropic":
        return _Probe(settings.credential_verify_anthropic_models_url, "anthropic")
    if provider == "nvidia":
        return _Probe(settings.credential_verify_nvidia_models_url, "bearer")
    return None


def _headers(style: HeaderStyle, key: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if style == "bearer":
        headers["Authorization"] = f"Bearer {key}"
    else:
        headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    return headers


def _interpret_response(
    provider: CredentialProvider,
    status_code: int,
) -> CredentialVerificationResult:
    if 200 <= status_code < 300:
        return CredentialVerificationResult(True, "provider accepted credential")
    if status_code in {401, 403}:
        raise CredentialVerificationFailed(
            "provider rejected credential",
            status_code=status_code,
        )
    if status_code == 429:
        return CredentialVerificationResult(
            None,
            "provider rate-limited verification; credential was not rejected",
        )
    if status_code in {404, 408, 500, 502, 503, 504}:
        raise CredentialVerificationUnavailable(
            f"{provider} verification endpoint unavailable",
        )
    raise CredentialVerificationFailed(
        "provider did not accept credential",
        status_code=status_code,
    )


def verify_provider_credential(
    provider: CredentialProvider,
    payload_kind: PayloadKind,
    payload: str,
    *,
    client: httpx.Client | None = None,
) -> CredentialVerificationResult:
    """Probe the provider endpoint with the decrypted credential payload."""
    probe = _probe_for(provider)
    if probe is None:
        return CredentialVerificationResult(
            None,
            f"provider verification unsupported for {provider}",
        )
    if payload_kind != "key":
        raise CredentialVerificationFailed(
            f"{provider} verification requires a key payload",
        )
    if not probe.url:
        return CredentialVerificationResult(
            None,
            f"provider verification not configured for {provider}",
        )

    if client is None:
        with httpx.Client(
            timeout=settings.credential_verify_timeout_seconds,
            follow_redirects=False,
        ) as scoped_client:
            return verify_provider_credential(
                provider,
                payload_kind,
                payload,
                client=scoped_client,
            )

    try:
        response = client.get(probe.url, headers=_headers(probe.header_style, payload))
    except httpx.HTTPError as exc:
        raise CredentialVerificationUnavailable(
            f"{provider} verification endpoint unavailable",
        ) from exc
    return _interpret_response(provider, response.status_code)


def verify_stored_credential(
    row: Mapping[str, Any],
    *,
    client: httpx.Client | None = None,
) -> CredentialVerificationResult:
    """Verify one repository credential row without exposing its plaintext."""
    return verify_provider_credential(
        cast(CredentialProvider, row["provider"]),
        cast(PayloadKind, row["payload_kind"]),
        crypto.decrypt(row["encrypted_payload"]),
        client=client,
    )
