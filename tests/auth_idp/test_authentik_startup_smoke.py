# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import httpx

from tests.auth_idp.authentik_live import AUTHENTIK_DOCKER_PYTESTMARK

pytestmark = AUTHENTIK_DOCKER_PYTESTMARK


def test_authentik_discovery_is_reachable(authentik_stack):
    response = httpx.get(authentik_stack.discovery_url, timeout=10.0)
    assert response.status_code == 200
    assert response.json()["issuer"].endswith("/application/o/nemo/")
