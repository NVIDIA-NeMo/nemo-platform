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
from .text_stats import TextStats
from .message_stats import MessageStats
from .numeric_stats import NumericStats
from .categorical_stats import CategoricalStats

__all__ = ["ColumnStats"]


class ColumnStats(BaseModel):
    """
    Measurements for one top-level column (keyed by name in ``PartitionProfile.stats``).

    The kind-specific block is populated by dtype; deep measurements fold into it (e.g.
    ``MessageStats.content_chars``) so stats stay flat — no path addressing to drift against the
    schema tree. Never row values — profiles stay safe to display / export without leaking data —
    with one role-gated exception: ``categorical.values``, and only for a column whose role makes it
    a controlled vocabulary rather than free text that happens to repeat.
    """

    categorical: Optional[CategoricalStats] = None
    """The vocabulary of a column that has one.

    Present only when the column really is a bounded controlled vocabulary. Absent
    otherwise, and the absence _is_ the claim: this column is not a vocabulary.

    It used to be a general cardinality count on every string and numeric column.
    Counting distinct values exactly means _retaining_ them, and for a column of
    prompts the set of distinct values is the column. What that bought was a reading
    of "9,954 distinct in 10,000 rows", which says free text, which `semantic_role`
    and the length quantiles already said for free. Nothing read it either: the only
    consumers of the number are a `<= 2` test that confirms a binary label and the
    `<= 32` gate on `values` below.

    The values themselves ARE row content, so they appear only for a column whose
    detected role makes it a controlled vocabulary — the assert-only-what-was-proven
    rule applied to the one place the profiler would otherwise leak the data it is
    describing.
    """

    messages: Optional[MessageStats] = None
    """Measurements for a `messages` column (a list of `{role, content}`)."""

    null_rate: Optional[float] = None

    numeric: Optional[NumericStats] = None
    """Measurements for a numeric column."""

    text: Optional[TextStats] = None
    """Measurements for a `string` column."""
