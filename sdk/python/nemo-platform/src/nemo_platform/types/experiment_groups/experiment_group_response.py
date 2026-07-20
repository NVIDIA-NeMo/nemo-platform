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

from typing import Dict, Optional
from datetime import datetime

from ..._models import BaseModel

__all__ = ["ExperimentGroupResponse"]


class ExperimentGroupResponse(BaseModel):
    """ExperimentGroup as served by the API."""

    id: str

    default_sort: str

    experiment_count: int
    """Deprecated alias for evaluation_count."""

    name: str

    workspace: str

    created_at: Optional[datetime] = None

    description: Optional[str] = None

    evaluation_count: Optional[int] = None
    """Number of live (non-soft-deleted) evaluations in this group."""

    insight_id: Optional[str] = None

    metadata: Optional[Dict[str, str]] = None

    summary: Optional[str] = None

    updated_at: Optional[datetime] = None
