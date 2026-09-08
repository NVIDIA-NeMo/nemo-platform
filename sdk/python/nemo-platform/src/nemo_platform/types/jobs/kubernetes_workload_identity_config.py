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

__all__ = ["KubernetesWorkloadIdentityConfig"]


class KubernetesWorkloadIdentityConfig(BaseModel):
    """Kubernetes workload identity token projection configuration."""

    token_audience: Optional[str] = None
    """Audience for the projected service account token.

    Defaults to auth.oidc.workload_client_id, auth.oidc.client_id, then
    'nemo-platform'.
    """

    token_expiration_seconds: Optional[int] = None
    """
    Requested expirationSeconds for the projected service account token used as the
    workload identity subject token.
    """
