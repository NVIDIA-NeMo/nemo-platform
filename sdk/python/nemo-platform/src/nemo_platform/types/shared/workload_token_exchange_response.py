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

__all__ = ["WorkloadTokenExchangeResponse"]


class WorkloadTokenExchangeResponse(BaseModel):
    """RFC 8693 token exchange response for workload identity access tokens."""

    access_token: str
    """JWT access token minted for the workload identity."""

    expires_in: int
    """Lifetime of the access token in seconds."""

    issued_token_type: str
    """Token type identifier for the issued token."""

    token_type: str
    """OAuth token type used in Authorization headers."""

    scope: Optional[str] = None
    """Space-separated scopes granted to the access token."""
