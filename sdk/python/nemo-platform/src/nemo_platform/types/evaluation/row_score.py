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

from typing import TYPE_CHECKING, Dict, List, Optional

from pydantic import Field as FieldInfo

from ..._models import BaseModel
from .metric_output import MetricOutput

__all__ = ["RowScore"]


class RowScore(BaseModel):
    """Normalized row-level score payload for metric/benchmark job results."""

    item: Dict[str, object]
    """Input item metadata for the evaluated row."""

    metrics: Dict[str, List[MetricOutput]]
    """Metric-level row outputs by metric key."""

    requests: List[Dict[str, object]]
    """Request details captured during evaluation."""

    sample: Dict[str, object]
    """Sample output payload for the evaluated row."""

    metric_errors: Optional[Dict[str, str]] = None
    """Full row-level error text keyed by metric for summary rendering."""

    row_index: Optional[int] = None
    """Stable row position used for result alignment."""

    if TYPE_CHECKING:
        # Some versions of Pydantic <2.8.0 have a bug and don’t allow assigning a
        # value to this field, so for compatibility we avoid doing it at runtime.
        __pydantic_extra__: Dict[str, object] = FieldInfo(init=False)  # pyright: ignore[reportIncompatibleVariableOverride]

        # Stub to indicate that arbitrary properties are accepted.
        # To access properties that are not valid identifiers you can use `getattr`, e.g.
        # `getattr(obj, '$type')`
        def __getattr__(self, attr: str) -> object: ...
    else:
        __pydantic_extra__: Dict[str, object]
