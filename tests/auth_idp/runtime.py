# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import uuid
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from tests.auth_idp.providers import ProviderConfig, load_provider_config


@lru_cache(maxsize=1)
def get_authentik_docker_test_runtime() -> ProviderConfig:
    provider = load_provider_config(Path("contrib/auth/authentik/manifest.yaml"))
    return replace(
        provider,
        nemo_config=Path("contrib/auth/authentik/config/platform-compose-authentik.yaml"),
        compose_project_name=f"authentik-e2e-{uuid.uuid4().hex[:8]}",
    )
