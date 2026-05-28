# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for parsing git remote URLs (HTTPS and SSH forms)."""

from __future__ import annotations

from urllib.parse import urlparse


def git_remote_host(url: str) -> str:
    """Return the hostname from a git remote URL, or "" if unparseable.

    Handles both schemed URLs (``https://github.com/org/repo``,
    ``ssh://git@github.com/org/repo``) and SSH alt form (``git@github.com:org/repo``).
    """
    if "://" in url:
        return (urlparse(url).hostname or "").lower()
    if "@" in url and ":" in url:
        return url.split("@", 1)[1].split(":", 1)[0].lower()
    return ""
