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

from typing import List, Optional
from datetime import datetime
from typing_extensions import Literal

from ..._models import BaseModel

__all__ = ["AccessKeyMetadataResponse"]


class AccessKeyMetadataResponse(BaseModel):
    """Metadata for a Scoped Access Key."""

    audiences: List[str]
    """Audiences accepted for the Scoped Access Key JWT."""

    created_at: datetime

    issuer: str
    """Issuer stamped into the Scoped Access Key JWT."""

    jti: str
    """Stable JWT ID for this Scoped Access Key."""

    principal: str
    """Principal ID stamped into the token."""

    status: Literal["ACTIVE", "EXPIRED", "REVOKED", "SUSPENDED", "ROTATING"]

    description: Optional[str] = None
    """Human-readable description of the Scoped Access Key."""

    entity_type: Optional[Literal["USER", "SERVICE_ACCOUNT"]] = None
    """Whether the key is bound to a user or a non-human service account."""

    expires_at: Optional[datetime] = None

    grace_period_expires_at: Optional[datetime] = None
    """Timestamp when the rotated-out key's grace period expires."""

    last_used_at: Optional[datetime] = None
    """
    Timestamp of the most recent successful authentication with this Scoped Access
    Key.
    """

    name: Optional[str] = None
    """Optional human-readable Scoped Access Key label."""
