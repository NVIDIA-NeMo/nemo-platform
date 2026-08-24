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

    Present only when the column really is a bounded controlled vocabulary. Absent otherwise, and
    the absence *is* the claim: this column is not a vocabulary.

    It used to be a general cardinality count on every string and numeric column. Counting distinct
    values exactly means *retaining* them, and for a column of prompts the set of distinct values is
    the column. What that bought was a reading of "9,954 distinct in 10,000 rows", which says free
    text, which ``semantic_role`` and the length quantiles already said for free. Nothing read it
    either: the only consumers of the number are a ``<= 2`` test that confirms a binary label and
    the ``<= 32`` gate on ``values`` below.

    The values themselves ARE row content, so they appear only for a column whose detected role makes
    it a controlled vocabulary — the assert-only-what-was-proven rule applied to the one place the
    profiler would otherwise leak the data it is describing.
    """

    distinct_count: int
    """How many distinct values the vocabulary holds.

    Exact, with no cap to have silently hit: this model is built only for a column
    that stayed inside the vocabulary bounds all the way through, so there is
    nothing to caveat. A small bounded set corroborates score / category roles, and
    `<= 2` is what confirms a binary preference label.
    """

    values: Optional[List[str]] = None
    """
    The observed values, present only when this column's `semantic_role` marks it a
    controlled vocabulary (label | provenance | meta | rank) and it holds at most 32
    of them. Cardinality alone cannot be the gate: it inverts on small data, where
    every column holds few distinct values — free text included — so a three-row
    dataset had its prompts stored verbatim. A role says what a column _is_, at any
    size. Read `PartitionProfile.rows_complete` to know whether this is the whole
    vocabulary or only what the sampled rows showed.
    """
