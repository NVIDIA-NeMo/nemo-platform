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
from .pareto_config import ParetoConfig

__all__ = ["ExperimentResponse"]


class ExperimentResponse(BaseModel):
    """Experiment as served by the API."""

    id: str

    default_sort: str

    name: str

    workspace: str

    created_at: Optional[datetime] = None

    description: Optional[str] = None

    evaluation_count: Optional[int] = None
    """Number of live (non-soft-deleted) evaluations in this experiment."""

    insight_id: Optional[str] = None

    metadata: Optional[Dict[str, str]] = None

    pareto: Optional[ParetoConfig] = None
    """Default X/Y metrics for a group's cost-vs-accuracy Pareto view.

    Metric ids use the same vocabulary as the evaluations list sort/filter fields —
    `cost_usd`, `latency_ms`, or `evaluators.<name>`. Defaults to cost (x) vs
    latency (y): both exist for every group, so the chart always has something to
    render before anyone customizes it.
    """

    summary: Optional[str] = None

    updated_at: Optional[datetime] = None
