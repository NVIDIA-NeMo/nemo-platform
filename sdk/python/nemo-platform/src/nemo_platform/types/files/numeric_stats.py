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

__all__ = ["NumericStats"]


class NumericStats(BaseModel):
    """
    Measurements for a numeric column: the range a score column spans, and where it sits in it.

    Carried as ``float`` whatever the column's width, so an integer column wider than 2**53 reports
    bounds that have lost their low bits. That is the score-column case this exists for -- ratings,
    ranks, labels -- and never the id-like case, which `CategoricalStats.distinct_count` is what
    identifies.
    """

    max: float
    """Largest value observed."""

    mean: float
    """Arithmetic mean over the values observed.

    With `min` and `max` it separates a rating concentrated at one end from one
    spread across the range, which a bare range cannot.
    """

    min: float
    """Smallest value observed."""
