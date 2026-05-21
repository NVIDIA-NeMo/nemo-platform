# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NAT plugin entry point for nemo-insights.

This module is discovered via the `[project.entry-points.'nat.plugins']` in
pyproject.toml. Importing it triggers tool registration with the NAT registry.
"""

import nemo_insights_plugin.tools.memory_writer  # noqa: F401
import nemo_insights_plugin.tools.onboarding  # noqa: F401
