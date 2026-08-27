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

from ..._models import BaseModel

__all__ = ["Quantiles"]


class Quantiles(BaseModel):
    """A per-row distribution summary.

    p99 = long-tail sequence-length signal; max = hard cap.

    The shape is the point, not the precision. Mean and max cannot tell "uniformly medium-length"
    apart from "mostly short with a long tail", and those call for opposite sequence budgets.

    **p50 / p95 / p99 are estimates, within a couple of percent**, read off counters bucketed by
    magnitude rather than off the lengths themselves. Every row is counted, so the *rank* is exact;
    only the value is rounded.

    **`max` is exact**, always, and is the only number here safe to treat as a hard bound.
    """

    max: int

    p50: int

    p95: int

    p99: int
