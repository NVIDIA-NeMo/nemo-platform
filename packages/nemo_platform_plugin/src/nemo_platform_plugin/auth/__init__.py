# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Plugin-safe auth primitives.

Subset of nmp.common.auth that doesn't require AuthClient / AuthConfig
(both of which pull heavy deps). The full server-side auth namespace
(middleware, client, permissions, etc.) lives in nmp.common.auth and
imports its building blocks back from here.
"""

from nemo_platform_plugin.auth.dependencies import (
    auth_client_context as auth_client_context,
)
from nemo_platform_plugin.auth.dependencies import (
    build_service_principal_headers as build_service_principal_headers,
)
from nemo_platform_plugin.auth.dependencies import (
    get_principal_auth_headers as get_principal_auth_headers,
)
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
from nemo_platform_plugin.auth.models import (
    NMP_PRINCIPAL_ENVVAR as NMP_PRINCIPAL_ENVVAR,
)
from nemo_platform_plugin.auth.models import (
    AuthContext as AuthContext,
)
from nemo_platform_plugin.auth.models import (
    Principal as Principal,
)
from nemo_platform_plugin.auth.tasks import (
    principal_from_env as principal_from_env,
)
