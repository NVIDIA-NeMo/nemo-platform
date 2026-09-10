# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# NOTE: This file is auto-generated
from __future__ import annotations

from nemo_platform_ext.cli.manifest import TopLevelEntry

API_TOP_LEVEL_ENTRIES = (
    TopLevelEntry(
        import_path=f"{__package__}.iam:app",
        name="iam",
        help="IAM operations.",
        panel="Core plugins",
        kind="group",
        hidden=True,
    ),
    TopLevelEntry(
        import_path=f"{__package__}.projects:app",
        name="projects",
        help="Manage projects.",
        panel="Core plugins",
        kind="group",
        hidden=True,
    ),
)
