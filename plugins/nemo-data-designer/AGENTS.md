<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# nemo-data-designer — Agent Instructions

## Skills

- **`refresh-data-designer-skill`** (`.agents/skills/refresh-data-designer-skill/SKILL.md`) → invoke when bumping the `data-designer` library version pin in `pyproject.toml`, when upstream ships skill changes that should land here, or when auditing drift. Refreshes the vendored skill bundle at `src/nemo_data_designer_plugin/skills/data-designer/`.
