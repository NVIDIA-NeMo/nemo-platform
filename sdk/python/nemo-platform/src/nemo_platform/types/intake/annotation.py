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

from typing import Dict, Optional
from datetime import datetime

from ..._models import BaseModel
from .annotation_kind import AnnotationKind

__all__ = ["Annotation"]


class Annotation(BaseModel):
    """Response model for annotation read endpoints."""

    annotation_id: str

    created_at: datetime

    ingested_at: datetime

    kind: AnnotationKind

    session_id: str

    workspace: str

    created_by: Optional[str] = None

    metadata: Optional[Dict[str, object]] = None

    name: Optional[str] = None

    span_id: Optional[str] = None

    text: Optional[str] = None

    value_numeric: Optional[float] = None

    value_text: Optional[str] = None
