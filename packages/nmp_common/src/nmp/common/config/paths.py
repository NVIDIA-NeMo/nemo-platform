# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""User-data path resolution for NeMo Platform local state.

Re-exports from :mod:`nemo_platform_plugin.config` — the canonical
implementation now lives in the plugin package.
"""

from nemo_platform_plugin.config import nmp_user_data_dir as nmp_user_data_dir

# Keep the env var constants exported for backward compat.
NMP_DATA_DIR_ENV_VAR = "NMP_DATA_DIR"
XDG_DATA_HOME_ENV_VAR = "XDG_DATA_HOME"
