# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolve the platform NGC API key from secrets or environment."""

from __future__ import annotations

import logging
import os
from typing import Any

from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.client.errors import NotFoundError
from nemo_platform_plugin.config import get_platform_config
from nemo_platform_plugin.secrets.client import AsyncSecretsClient

logger = logging.getLogger(__name__)


async def resolve_ngc_api_key(sdk: Any) -> str | None:
    """Resolve NGC API key from ``platform.ngc_api_key_secret`` or env fallback."""
    platform = get_platform_config()
    secret_ref = platform.ngc_api_key_secret.strip()
    env_var = platform.ngc_api_key_env_var
    if not secret_ref:
        return os.environ.get(env_var) or None

    parts = secret_ref.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        logger.warning(
            "platform.ngc_api_key_secret must be 'workspace/name'; got %r; falling back to env",
            secret_ref,
        )
        return os.environ.get(env_var) or None

    workspace, name = parts[0], parts[1]
    try:
        secrets = client_from_platform(sdk, AsyncSecretsClient)
        response = (await secrets.access_secret(name=name, workspace=workspace)).data()
        if response.value:
            logger.debug("Resolved NGC API key from secret %s/%s", workspace, name)
            return response.value
        logger.warning(
            "Secret has no data; falling back to env",
            extra={"workspace": workspace, "secret_name": name, "env_var": env_var},
        )
        return os.environ.get(env_var) or None
    except NotFoundError:
        logger.info(
            "NGC API key secret not found; falling back to env",
            extra={"workspace": workspace, "secret_name": name, "env_var": env_var},
        )
        return os.environ.get(env_var) or None
    except Exception as exc:
        logger.warning(
            "Failed to resolve NGC API key from secret; falling back to env",
            extra={"workspace": workspace, "secret_name": name, "error": str(exc)},
        )
        return os.environ.get(env_var) or None
