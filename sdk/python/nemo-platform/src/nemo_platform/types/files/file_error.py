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

__all__ = ["FileError"]


class FileError(BaseModel):
    """A file the profiler could not fully use, and why.

    Only failures are enumerated. Healthy files are counted (``SplitProfile.num_files``), because a
    per-file record for each scaled the profile with shard count while telling a reader nothing: at
    512 shards those records were 95% of the payload.
    """

    error: str
    """
    Why this file was not fully read: unreadable, corrupt, partially parsed, or in a
    format with no reader. A file that was read cleanly never appears here, so the
    absence of a path is itself the claim that it was fine.
    """

    path: str
    """Relative path within the fileset."""
