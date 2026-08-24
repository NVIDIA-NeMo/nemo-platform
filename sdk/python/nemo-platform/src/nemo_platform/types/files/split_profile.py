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

    Resolution precedence (declared structure beats detection):

    1. HF card front-matter when the fileset ships a README — ``configs[].data_files`` maps splits to
       file globs explicitly;
    2. best-effort detection from file paths (train/test/validation markers, sharded layouts like
       ``data/train-00000-of-00003.parquet``); path markers are matched against canonical names and
       common aliases (val/valid/dev -> validation), the normalized concept lands in ``canonical``, and
       the split keeps its on-disk ``name``;
    3. otherwise leave it alone: a single "default" split holding all files.

    A split encoded as a *data column* (a value inside each row rather than a file grouping) is not
    resolved here; such files profile as a single split.
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
    "helpsteer2/train\\**.parquet". Gives the files back their addressability without
    giving back the per-file manifest — one pattern per split, whatever the shard
    count — so a consumer can hand a reader the files of one split without listing
    the fileset and re-deriving which shards belong where. Named for HF card
    front-matter's `configs[].data_files`, which is the declared form of this same
    claim and, once cards are parsed, the thing that will replace this inference
    rather than sit beside it in a second vocabulary.

    `*` spans any run of characters except `/` — the one reading shared by shell
    globs, Python's glob, fsspec and HF — so the pattern means the same thing
    wherever it is pasted. `**` is never emitted, because its meaning is not shared.

    None when no single pattern selects these files and nothing else (shards spread
    across subdirectories, say). Never approximate: a pattern is emitted only after
    being matched back against every file in the fileset and found to select this
    split exactly. A glob is an instruction to go read files, so a near miss is not
    a rougher answer — it silently pulls a README, or a neighbouring split's shards,
    into a training set.
    """

    num_examples: Optional[int] = None
    """
    Rows in this split, counting every one of its files whether or not that file's
    rows were read. Always exact — summed from parquet footers or from files read to
    their end — and None the moment any one file's count is unknown. Never an
    estimate, so it carries no accuracy caveat: a capped run still reports the true
    total whenever the footers knew it.
    """

    num_files: Optional[int] = None
    """How many files resolved into this split.

    Partitioning is exhaustive and disjoint — each file of the partition lands in
    exactly one split — so these sum to the partition's file count. A count rather
    than a list: the paths of healthy shards are the one part of a profile that
    grows without bound and informs no decision.
    """

    size_bytes: Optional[int] = None
    """On-disk bytes of this split's files, summed.

    Answers whether the data fits wherever the reader means to put it — the first
    question asked of an unfamiliar dataset, and one a row count cannot answer,
    since a row ranges from an integer score to a reasoning trace. Unlike
    `num_examples` this is never None: it comes from the file listing rather than
    from reading, so a file that failed mid-read still contributes its size. Bytes
    as stored — compressed, and several times this once decoded into memory. Covers
    only files a partition grouped; a format with no reader never reaches a split,
    so weigh the whole fileset with `SamplingInfo.bytes_present`.
    """
