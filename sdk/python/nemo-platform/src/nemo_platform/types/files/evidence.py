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

__all__ = ["Evidence"]


class Evidence(BaseModel):
    """Why the profiler believes what it detected.

    Captured at profile time — the only moment it is cheap and guaranteed to match the stored
    result; once the data or the profiler version moves, a re-run explains the *new* snapshot, not
    the stored one.
    """

    detail: str
    """Self-describing evidence, e.g.

    "answer matches '#### <number>' in 100% of 1024 sampled rows".
    """

    kind: str
    """
    column_name | column_dtype | content_probe | split_name | file_name |
    card_metadata | user_hint | error — `user_hint` for a caller-supplied column
    role the data could not support, and `error` for when a detector could not run
    at all, so an absent finding is distinguishable from a finding of absence.
    """
