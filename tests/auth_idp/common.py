# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import os

import pytest

from tests.auth_idp.runtime_contract import AuthIdpCase


def jwt_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))
    if not isinstance(decoded, dict):
        return {}
    return decoded


def require_capability(case: AuthIdpCase, capability: str) -> None:
    if capability not in case.capabilities:
        pytest.skip(f"{case.id} does not declare auth-idp capability: {capability}")


def nmp_api_image() -> str:
    registry = os.environ.get("IMAGE_REGISTRY", "my-registry")
    tag = os.environ.get("BAKE_TAG", "local")
    return f"{registry}/nmp-api:{tag}"
