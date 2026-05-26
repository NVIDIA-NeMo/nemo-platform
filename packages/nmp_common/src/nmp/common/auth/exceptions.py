# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Backward-compat re-exports — canonical home is nemo_platform_plugin.auth.exceptions."""

from nemo_platform_plugin.auth.exceptions import (
    AuthorizationError as AuthorizationError,
)
from nemo_platform_plugin.auth.exceptions import (
    InvalidPermissionFormatError as InvalidPermissionFormatError,
)
from nemo_platform_plugin.auth.exceptions import (
    InvalidPrincipalHeader as InvalidPrincipalHeader,
)
from nemo_platform_plugin.auth.exceptions import (
    InvalidScopeFormatError as InvalidScopeFormatError,
)
