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

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict

__all__ = ["AccessKeyCreateParams"]


class AccessKeyCreateParams(TypedDict, total=False):
    description: Optional[str]
    """Optional human-readable description of the Scoped Access Key."""

    expires_in_seconds: Optional[int]
    """Scoped Access Key lifetime in seconds.

    Omit to use auth.access_keys.default_expires_in_seconds. Send explicit null to
    request a non-time-delimited key, which requires
    auth.access_keys.max_expires_in_seconds to be disabled.
    """

    name: Optional[str]
    """Optional human-readable Scoped Access Key label.

    The token jti remains the stable identifier.
    """
