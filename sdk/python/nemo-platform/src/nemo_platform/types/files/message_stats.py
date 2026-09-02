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
    opposite sequence budgets.

    **p50 / p95 / p99 are estimates, within a couple of percent**, read off counters
    bucketed by magnitude rather than off the lengths themselves. Every row is
    counted, so the _rank_ is exact; only the value is rounded.

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
    opposite sequence budgets.

    **p50 / p95 / p99 are estimates, within a couple of percent**, read off counters
    bucketed by magnitude rather than off the lengths themselves. Every row is
    counted, so the _rank_ is exact; only the value is rounded.

    **`max` is exact**, always, and is the only number here safe to treat as a hard
    bound.
    """

    valid_alternation_rate: float

    has_tool_calls: Optional[bool] = None

    roles_seen: Optional[List[str]] = None
    """The distinct role strings present in the sampled rows -- e.g.

    ["system", "user", "assistant", "tool"], but equally ["human", "gpt"]. A
    measurement of row content, not a closed vocabulary: an unexpected role is the
    finding worth reporting, and normalizing it away would hide what a consumer
    needs before choosing a chat template. This is row content in the stored
    profile, under no role gate, so it is bounded twice: a column showing more
    distinct roles than fit here is not a chat column, and each string is truncated
    to a fixed length -- a role is a short token by nature, so anything long enough
    to be truncated is itself the finding. Do not match on these exactly; a value
    may be a prefix.
    """
