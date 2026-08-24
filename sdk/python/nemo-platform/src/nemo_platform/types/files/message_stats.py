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

from ..._models import BaseModel
from .quantiles import Quantiles

__all__ = ["MessageStats"]


class MessageStats(BaseModel):
    """Measurements for a ``messages`` column (a list of ``{role, content}``)."""

    content_chars: Quantiles
    """A per-row distribution summary.

    p99 = long-tail sequence-length signal; max = hard cap.

    The shape is the point, not the precision. Mean and max cannot tell "uniformly
    medium-length" apart from "mostly short with a long tail", and those call for
    opposite sequence budgets — set one from `max` and most of the memory is wasted,
    set it from the mean and the tail is silently truncated. Reading p50 against p99
    is what answers it.

    **p50 / p95 / p99 are estimates, within a couple of percent.** They are read off
    counters bucketed by magnitude rather than from the lengths themselves, which is
    what keeps the profiler's memory flat in rows. Every row is counted, so the
    _rank_ is exact; only the value is rounded, and it is rounded to a bound that
    does not grow with the dataset. That is the cheap error to accept here, because
    whoever reads these rounds to a power of two anyway.

    **`max` is exact**, always, and is the only number here safe to treat as a hard
    bound.
    """

    ends_with_assistant_rate: float
    """
    Key signal separating an SFT target (conversation ends on an assistant turn)
    from a prompt-only row.
    """

    turns: Quantiles
    """A per-row distribution summary.

    p99 = long-tail sequence-length signal; max = hard cap.

    The shape is the point, not the precision. Mean and max cannot tell "uniformly
    medium-length" apart from "mostly short with a long tail", and those call for
    opposite sequence budgets — set one from `max` and most of the memory is wasted,
    set it from the mean and the tail is silently truncated. Reading p50 against p99
    is what answers it.

    **p50 / p95 / p99 are estimates, within a couple of percent.** They are read off
    counters bucketed by magnitude rather than from the lengths themselves, which is
    what keeps the profiler's memory flat in rows. Every row is counted, so the
    _rank_ is exact; only the value is rounded, and it is rounded to a bound that
    does not grow with the dataset. That is the cheap error to accept here, because
    whoever reads these rounds to a power of two anyway.

    **`max` is exact**, always, and is the only number here safe to treat as a hard
    bound.
    """

    valid_alternation_rate: float

    has_tool_calls: Optional[bool] = None

    roles_seen: Optional[List[str]] = None
    """The distinct role strings actually present in the sampled rows, verbatim — e.g.

    ["system", "user", "assistant", "tool"], but equally ShareGPT's ["human", "gpt"]
    or a house convention. A measurement of row content, not a vocabulary the
    profiler picks from, so it is deliberately not an enum: an unexpected role is
    the finding worth reporting, and normalizing or dropping it would hide exactly
    what a consumer needs to see before choosing a chat template. Bounded: this is
    fed straight from row content, and a column with more distinct roles than fit
    here is not a chat column, which the first few dozen already say.
    """
