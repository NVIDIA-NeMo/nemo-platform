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

from typing import List

from ..._models import BaseModel
from .pareto_config import ParetoConfig
from .pareto_metric_point import ParetoMetricPoint

__all__ = ["ParetoDataResponse"]


class ParetoDataResponse(BaseModel):
    """
    Everything the Pareto chart needs for a group: the configured default axes plus one point per
    evaluation (cost/latency/evaluator means). Unpaginated and slim — the client plots the whole set
    and computes the frontier from any two metrics without refetching.
    """

    pareto: ParetoConfig
    """Default X/Y metrics for a group's cost-vs-accuracy Pareto view.

    Metric ids use the same vocabulary as the evaluations list sort/filter fields —
    `cost_usd`, `latency_ms`, or `evaluators.<name>`. Defaults to cost (x) vs
    latency (y): both exist for every group, so the chart always has something to
    render before anyone customizes it.
    """

    points: List[ParetoMetricPoint]
    """One point per live evaluation in the group."""
