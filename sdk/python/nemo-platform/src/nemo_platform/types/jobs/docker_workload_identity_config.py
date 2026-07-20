# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# File generated from our OpenAPI spec by Stainless. See CONTRIBUTING.md for details.

from typing import Optional

from ..._models import BaseModel

__all__ = ["DockerWorkloadIdentityConfig"]


class DockerWorkloadIdentityConfig(BaseModel):
    """Docker-only subject token issuer configuration for workload identity."""

    client_id: Optional[str] = None
    """OAuth client ID used by the Docker demo issuer.

    Defaults to auth.oidc.workload_client_id or auth.oidc.client_id.
    """

    enabled: Optional[bool] = None
    """Enable Docker workload identity token-file injection.

    Defaults to auth.oidc.workload_token_exchange_enabled.
    """

    password_env_var: Optional[str] = None
    """
    Controller environment variable that contains the Docker demo issuer password
    grant shared secret.
    """

    refresh_margin_seconds: Optional[int] = None
    """
    Seconds before subject-token expiry when the Docker refresher issues a
    replacement token.
    """

    scope: Optional[str] = None
    """OAuth scope for the Docker demo issuer."""

    subject_token_ttl_seconds: Optional[int] = None
    """
    Fallback subject-token lifetime when the Docker demo issuer response omits
    expires_in.
    """

    token_endpoint: Optional[str] = None
    """OAuth token endpoint used by the Docker demo issuer.

    Defaults to auth.oidc.token_endpoint.
    """

    username: Optional[str] = None
    """Username for the Docker demo issuer password grant."""
