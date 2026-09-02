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

__all__ = ["CategoricalStats"]


class CategoricalStats(BaseModel):
    """The vocabulary of a column that has one.

    Present only when the column really is a bounded controlled vocabulary. Absent otherwise, and the
    absence *is* the claim: this column is not a vocabulary.

    Not a general cardinality count -- counting distinct values exactly means *retaining* them, and
    for a column of prompts the distinct set is the column. The number has two consumers: a ``<= 2``
    test confirming a binary label, and the ``<= 32`` gate on ``values``.
    """

    distinct_count: int
    """How many distinct values the vocabulary holds.

    Present only for a column that stayed a bounded vocabulary throughout -- absence
    means the column is not one, not that counting was skipped. Exact over the rows
    that were read; where the partition's `rows_complete` is false, a shard was
    missed or a read was cut short, and this is a LOWER BOUND for the partition.
    """

    values: Optional[List[str]] = None
    """
    The observed values, present only when this column's `semantic_role` makes it a
    controlled vocabulary and the count is small enough to quote. Absent whenever
    any file in the partition was read only part-way -- by a row budget or by a
    failure mid-read -- since a prefix cannot prove an enumeration and quoting one
    would store a sample of row content as though it were the whole vocabulary. A
    partition that lost a shard before it yielded a row still quotes: that file
    contributed nothing to measure, so the values gathered from the rest are entire,
    and `rows_complete` reports the loss. This is the one place _column_ content
    reaches the stored profile under a role gate rather than a size gate, since
    cardinality inverts on small data, where every column looks like an enumeration.
    It is not the only place row content reaches the profile: see
    `MessageStats.roles_seen`.
    """
