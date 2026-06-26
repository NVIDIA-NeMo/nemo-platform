# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for docker-backed integration tests."""

from __future__ import annotations

import time
from typing import Any


def force_remove_container(client: Any, name: str, *, retries: int = 3) -> None:
    """Remove a container, tolerating concurrent cleanup from other tests."""
    from docker.errors import APIError, NotFound

    for attempt in range(retries):
        try:
            client.containers.get(name).remove(force=True)
            return
        except NotFound:
            return
        except APIError as exc:
            if "already in progress" in str(exc).lower() and attempt + 1 < retries:
                time.sleep(0.5)
                continue
            if "already in progress" in str(exc).lower():
                return
            raise
