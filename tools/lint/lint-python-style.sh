#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail
# Check Python style with ruff (lint and format).
# Uses the ruff version pinned in pyproject.toml dev dependencies.
uv run ruff check
uv run ruff format --check
