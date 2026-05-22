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

from typing import Dict
from typing_extensions import Required, TypedDict

from .annotation_kind import AnnotationKind

__all__ = ["AnnotationCreateParams"]


class AnnotationCreateParams(TypedDict, total=False):
    workspace: str

    kind: Required[AnnotationKind]

    session_id: Required[str]
    """Session id this annotation belongs to.

    Required even for span-targeted annotations for session-locality reads.
    """

    metadata: Dict[str, object]

    name: str

    span_id: str
    """Target span id.

    Optional when annotating a whole session. Loose target policy — not validated.
    """

    text: str

    value_numeric: float

    value_text: str
