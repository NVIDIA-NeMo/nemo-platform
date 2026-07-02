# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared harness state: identities, workspace names, and the platform handle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
from idp import MiniOIDCIssuer, MintSpec

ADMIN_EMAIL = "admin@harness.test"
WS_A = "authz-e2e-wsa"
WS_B = "authz-e2e-wsb"

# sub / email for every identity in the matrix (bindings provisioned in conftest).
IDENTITIES: dict[str, dict] = {
    "admin": {"sub": "usr-admin", "email": ADMIN_EMAIL},
    "alice": {"sub": "usr-alice", "email": "alice@harness.test"},
    "victor": {"sub": "usr-victor", "email": "victor@harness.test"},
    "sam": {"sub": "usr-sam", "email": "sam@harness.test"},
    "nobody": {"sub": "usr-nobody", "email": "nobody@harness.test"},
    "service": {"sub": "service:probe", "email": None},
    "provisioner": {"sub": "service:e2e-harness", "email": None},
}


@dataclass
class Platform:
    """Handle to a spawned ``nemo services run`` instance under test."""

    base_url: str
    issuer: MiniOIDCIssuer
    log_path: Path

    def token(self, identity: str, *, scopes: list[str] | None = None, **overrides) -> str:
        info = IDENTITIES[identity]
        spec = MintSpec(sub=info["sub"], email=info["email"], scopes=scopes or [], **overrides)
        return self.issuer.mint(spec)

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        body: dict | None = None,
    ) -> httpx.Response:
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        return httpx.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            json=body,
            timeout=30.0,
        )
