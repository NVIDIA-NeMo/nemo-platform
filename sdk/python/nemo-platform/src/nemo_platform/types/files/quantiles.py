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
    apart from "mostly short with a long tail", and those call for opposite sequence budgets — set
    one from `max` and most of the memory is wasted, set it from the mean and the tail is silently
    truncated. Reading p50 against p99 is what answers it.

    **p50 / p95 / p99 are estimates, within a couple of percent.** They are read off counters bucketed
    by magnitude rather than from the lengths themselves, which is what keeps the profiler's memory
    flat in rows. Every row is counted, so the *rank* is exact; only the value is rounded, and it is
    rounded to a bound that does not grow with the dataset. That is the cheap error to accept here,
    because whoever reads these rounds to a power of two anyway.

    **`max` is exact**, always, and is the only number here safe to treat as a hard bound.
    """

    max: int

    p50: int

    p95: int

    p99: int
