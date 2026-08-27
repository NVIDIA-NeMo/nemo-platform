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

from typing import Dict, List, Optional

from ..._models import BaseModel
from .column_stats import ColumnStats
from .split_profile import SplitProfile
from .partition_classification import PartitionClassification

__all__ = ["PartitionProfile"]


class PartitionProfile(BaseModel):
    """
    A file-group sharing one row schema and one source directory (roughly an HF config).

    File membership and row counts live on ``splits`` — every file lands in exactly one split, so
    partition-level files / num_examples would be derivable duplication.
    """

    classification: PartitionClassification
    """
    What the data _is_, described objectively — the stored basis a downstream reader
    uses to decide which tasks the dataset can train.

    Holds the partition-level findings only: column-level semantics are the
    `semantic_role` markers on the feature nodes they describe, but the evidence for
    _why_ they were assigned is recorded here.
    """

    features: List["FeatureSchema"]
    """
    The row schema: measured layout plus detected role markers, derived de novo
    (nested).
    """

    rows_complete: bool
    """True => every row of every file in THIS partition was read.

    Only then can a consumer assert enum / required in a bridged JSON Schema, or
    read a verifiability coverage of 1.0 as literal.

    It says whether anything was missed on the way in, not whether a given number is
    exact -- that is a property of the number, and each one says so. Scoped to the
    partition, because a corrupt shard in one says nothing about the measurements in
    another.
    """

    splits: List[SplitProfile]
    """Path-detected, else a single 'default' split."""

    file_formats: Optional[List[str]] = None
    """The distinct formats this partition's files are in, sorted -- normally one.

    Observed rather than chosen: a directory holding two formats has a stray file,
    not a second dataset, and splitting the partition to keep a single value true
    made partition names unstable.
    """

    name: Optional[str] = None
    """Identifies this partition, and unique within a profile.

    The path prefix its files share within the fileset: a top-level directory, or ""
    when they sit at the fileset root. Empty is a safe sentinel because no directory
    can be named it. Once card front-matter is parsed, a declared config name
    populates this instead. For display, read it as `name or "default"` rather than
    storing that default, which would throw away the only thing identifying the
    partition.
    """

    stats: Optional[Dict[str, ColumnStats]] = None
    """
    Top-level column name -> measurements; sparse (a column with nothing worth
    measuring is omitted); keys are a subset of the top-level `features` names.
    """


from .feature_schema import FeatureSchema
