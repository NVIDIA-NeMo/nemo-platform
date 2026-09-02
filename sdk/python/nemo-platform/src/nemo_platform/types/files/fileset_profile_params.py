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

from __future__ import annotations

from typing_extensions import TypedDict

__all__ = ["FilesetProfileParams"]


class FilesetProfileParams(TypedDict, total=False):
    workspace: str

    row_budget: int
    """
    Rows the profiler may read per _partition_, divided across that partition's
    files rather than applied to each one. Omit (or pass 0) to read every row, which
    is the default: the profiler folds, so memory is flat in rows and an exhaustive
    read buys exact row counts, proven value enumerations, and `rows_complete`. Set
    a budget when the fileset is large enough that the transfer is the cost worth
    bounding — files are read over the network, so an uncapped run pulls every row
    group over the wire. Named to match the profiler's own `row_budget`, which is
    the value this becomes.
    """
