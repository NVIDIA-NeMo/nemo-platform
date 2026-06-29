# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

AUTHENTIK_DOCKER_E2E_CONFIG = pytest.mark.e2e_config(
    "contrib/auth/authentik/config/platform-compose-authentik.yaml",
    {
        "e2e_sidecars": {
            "authentik": {
                "provider": "authentik",
            }
        }
    },
)

AUTHENTIK_DOCKER_PYTESTMARK = [
    pytest.mark.auth_idp,
    AUTHENTIK_DOCKER_E2E_CONFIG,
    pytest.mark.xdist_group("idp-live"),
]
