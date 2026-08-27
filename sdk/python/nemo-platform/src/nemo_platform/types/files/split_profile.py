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

__all__ = ["SplitProfile"]


class SplitProfile(BaseModel):
    """A split within a partition.

    Resolved from file paths (train/test/validation markers, sharded layouts). Markers are matched
    against canonical names and common aliases (val/valid/dev -> validation); the normalized concept
    lands in ``canonical`` and the split keeps its on-disk ``name``. Failing any marker, a single
    "default" split holds all files.

    A dataset card's ``configs[].data_files`` would take precedence over that, mapping splits to
    globs explicitly rather than by inference -- but card parsing is not implemented, so path
    detection is the only source today, and ``card_metadata`` is a kind no evidence yet carries.

    A split encoded as a *data column* rather than a file grouping is not resolved here.
    """

    name: str
    """The on-disk name: train | test | train_prefs | ..."""

    canonical: Optional[str] = None
    """Normalized concept: train | validation | test; None when nothing matches.

    E.g. train_prefs -> train, with the variant's intent kept in `name`.
    """

    data_files: Optional[str] = None
    """
    A glob selecting exactly this split's files, relative to the fileset root:
    "helpsteer2/train\\**.parquet". One pattern per split whatever the shard count, so
    a consumer can read one split without listing the fileset and re-deriving which
    shards belong where. Named for HF card front-matter's `configs[].data_files`.

    `*` spans any run of characters except `/` -- the reading shared by shell globs,
    Python's glob, fsspec and HF. `**` is never emitted, because its meaning is not
    shared.

    None when no single pattern selects these files and nothing else. Never
    approximate: a pattern is emitted only after being matched against every file in
    the fileset and found to select this split exactly, since a near miss would
    silently pull in a README or a neighbouring split's shards.
    """

    num_examples: Optional[int] = None
    """
    Rows in this split, counting every one of its files whether or not that file was
    read to the end. None when any file's count is unknown, which is the honest
    answer: the sum of the rest would look like a fact and read low.
    """

    num_files: Optional[int] = None
    """How many files resolved into this split.

    Partitioning is exhaustive over the partition's data files, so these sum to the
    partition's total.
    """

    size_bytes: Optional[int] = None
    """On-disk bytes of this split's files, summed.

    Answers whether the data fits wherever the reader means to put it, which a row
    count cannot: a row ranges from an integer score to a reasoning trace. Never
    None, since it comes from the file listing rather than from reading. Bytes as
    stored -- compressed, and several times this once decoded.
    """
