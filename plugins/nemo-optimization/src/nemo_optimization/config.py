# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Job-id helper for the Agents optimize lane."""

from __future__ import annotations

import uuid


def generate_optimize_id() -> str:
    """Return a unique optimize job / experiment id (``optimize-<12 hex>``)."""
    return f"optimize-{uuid.uuid4().hex[:12]}"
