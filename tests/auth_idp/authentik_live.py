# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

AUTHENTIK_COMPOSE_PROJECT_NAME = "authentik-e2e"
AUTHENTIK_WORKLOAD_NETWORK_NAME = f"{AUTHENTIK_COMPOSE_PROJECT_NAME}_workload"
AUTHENTIK_NEMO_DIRECT_PORT = "38081"

AUTHENTIK_DOCKER_E2E_CONFIG = pytest.mark.e2e_config(
    "contrib/auth/authentik/config/platform-compose-authentik.yaml",
    {
        "auth": {
            "oidc": {
                "additional_issuers": [
                    "http://authentik-server:9000/application/o/nemo/",
                    "http://127.0.0.1:38080/application/o/nemo-cli/",
                    "http://127.0.0.1:38080/application/o/nemo/",
                ],
                "token_endpoint": "http://127.0.0.1:38080/application/o/token/",
                "device_authorization_endpoint": "http://127.0.0.1:38080/application/o/device/",
            }
        },
    },
    harness={
        "backend": "docker_compose",
        "compose_file": "contrib/auth/authentik/docker-compose.yml",
        "compose_project_name": AUTHENTIK_COMPOSE_PROJECT_NAME,
        "service_url": "http://127.0.0.1:38080",
        "auth_ready_url": f"http://127.0.0.1:{AUTHENTIK_NEMO_DIRECT_PORT}",
        "wait_url": "http://127.0.0.1:38080/application/o/nemo/.well-known/openid-configuration",
        "env": {
            "AUTHENTIK_GATEWAY_PORT": "38080",
            "NEMO_DIRECT_PORT": AUTHENTIK_NEMO_DIRECT_PORT,
            "AUTHENTIK_WORKLOAD_NETWORK_NAME": AUTHENTIK_WORKLOAD_NETWORK_NAME,
        },
    },
)

AUTHENTIK_DOCKER_PYTESTMARK = [
    pytest.mark.auth_idp,
    AUTHENTIK_DOCKER_E2E_CONFIG,
    pytest.mark.xdist_group("idp-live"),
]
