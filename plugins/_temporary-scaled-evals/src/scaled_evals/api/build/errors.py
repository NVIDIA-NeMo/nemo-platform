# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared build exceptions."""

from __future__ import annotations


class BuildError(RuntimeError):
    """A container image build failed; the message carries the actionable detail."""
