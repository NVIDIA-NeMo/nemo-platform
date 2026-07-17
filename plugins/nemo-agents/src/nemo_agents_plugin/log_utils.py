# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Logging helpers."""

from __future__ import annotations


def scrub(value: object) -> str:
    """Strip CR/LF from *value* so user-controlled text can't forge log lines."""
    return str(value).replace("\r", "").replace("\n", "")
