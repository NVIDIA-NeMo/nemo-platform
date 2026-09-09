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
from datetime import datetime
from typing_extensions import Literal

from ..._models import BaseModel
from .access_key_create_response import AccessKeyCreateResponse

__all__ = ["AccessKeyRotateResponse"]


class AccessKeyRotateResponse(BaseModel):
    """Response returned after rotating a Scoped Access Key.

    The rotated-out key (``previous_jti``) remains usable for ``grace_period_seconds``
    (the dual-active grace period) so callers can cut traffic over to ``new_key``
    before the old key is treated as revoked.
    """

    grace_period_seconds: int
    """Seconds the rotated-out key remains usable before it is treated as revoked."""

    new_key: AccessKeyCreateResponse
    """Create response. The token value is returned only once."""

    previous_jti: str
    """Stable JWT ID of the Scoped Access Key that was rotated out."""

    previous_status: Literal["ACTIVE", "EXPIRED", "REVOKED", "SUSPENDED", "ROTATING"]
    """Effective status of the rotated-out key immediately after this request.

    Normally ROTATING, but may already read as REVOKED or EXPIRED if reconciling
    this request's outcome was itself delayed past the grace deadline or a
    concurrent revoke.
    """

    grace_period_expires_at: Optional[datetime] = None
    """Timestamp when the rotated-out key's grace period expires."""
