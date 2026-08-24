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

    Named for what it measures. It was `stats_complete`, which promised more than it
    delivered: `Quantiles` is an estimate by construction however much was read,
    bounded for the cost reason its own docstring gives. Whether a number is exact
    is a property of that number, and every one of them says so; this says only
    whether anything was missed on the way in.

    Scoped to the partition because that is where it is decided — a corrupt shard in
    one partition says nothing about the measurements in another, and a fileset-wide
    flag quietly downgraded every partition to the worst one.
    """

    splits: List[SplitProfile]
    """card-declared > path-detected > single 'default' split."""

    file_formats: Optional[List[str]] = None
    """
    The distinct formats this partition's files are in, sorted — normally exactly
    one, and more than one when a stray .jsonl sits beside .parquet shards. That is
    noise, not a second dataset, so it stays in this partition and shows up here
    rather than splitting it. jsonl | parquet are read today; csv | arrow are
    reserved vocabulary the profiler cannot read yet and reports on
    `DatasetProfile.file_errors` instead.
    """

    name: Optional[str] = None
    """Identifies this partition, and unique within a profile.

    It is the path prefix its files share within the fileset: a top-level directory,
    or "" when they sit at the fileset root. Empty is a safe sentinel precisely
    because no directory can be named it, so root-level files stay distinct from a
    directory literally called 'default'. Once card front-matter is parsed, a
    declared config name populates this field instead — the same claim from a better
    source. For display, read it as `name or "default"`: storing that default was a
    lossy habit, because a lone partition under `data/` then reported "default" and
    threw away the only thing identifying it.
    """

    stats: Optional[Dict[str, ColumnStats]] = None
    """
    Top-level column name -> measurements; sparse (a column with nothing worth
    measuring is omitted); keys are a subset of the top-level `features` names.
    """


from .feature_schema import FeatureSchema
