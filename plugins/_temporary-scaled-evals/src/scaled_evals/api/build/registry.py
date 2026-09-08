# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Image registry readiness for task finalize (BuildKit push target)."""

from __future__ import annotations

import httpx

from scaled_evals.api.settings import settings

_READYZ_TIMEOUT_SECONDS = 3.0


def _registry_v2_base_url() -> str:
    """Docker Registry HTTP API v2 root (``/v2/``) for ``settings.image_registry``."""
    reg = settings.image_registry.strip()
    if "://" in reg:
        return reg.rstrip("/")
    scheme = "http" if settings.registry_insecure else "https"
    return f"{scheme}://{reg}"


def check_registry() -> None:
    """Confirm the image registry responds to ``GET /v2/``.

    Pairs with :func:`buildkit.check_buildkit` for the task finalize path.
    Raises on failure; used by ``GET /v1/readyz``.
    """
    url = f"{_registry_v2_base_url()}/v2/"
    try:
        resp = httpx.get(url, timeout=_READYZ_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise RuntimeError(str(exc)) from exc
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}")
