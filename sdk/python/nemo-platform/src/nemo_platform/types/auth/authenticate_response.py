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
from typing_extensions import Literal

from ..._models import BaseModel

__all__ = ["AuthenticateResponse"]


class AuthenticateResponse(BaseModel):
    """Successful bearer token authentication response for auth callouts."""

    principal: str

    token_kind: Literal["access_key", "oidc_access_token", "workload_access_token", "workload_subject_token"]

    email: Optional[str] = None

    groups: Optional[List[str]] = None

    jti: Optional[str] = None

    scopes: Optional[List[str]] = None
