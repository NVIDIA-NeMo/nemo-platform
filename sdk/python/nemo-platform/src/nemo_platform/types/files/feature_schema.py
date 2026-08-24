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

from typing import List, Optional

from ..._models import BaseModel

__all__ = ["FeatureSchema"]


class FeatureSchema(BaseModel):
    """
    One node of the row schema, derived de novo from the data (there is no external JSON-Schema
    store to reference). Carries the measured layout (name, dtype, children) plus at most one
    detected ``semantic_role`` marker stacked on the same node.

    Recursive and fully expanded: a ``struct`` node has child ``fields``; a ``list`` / ``messages``
    node has an element ``items`` — for ``messages`` the per-message ``{role, content}`` struct is
    spelled out, so a vision message whose content is a list of typed parts shows up structurally.
    The column-level chat summary lives in ``MessageStats`` on the stats side. This tree is the
    clean, bridgeable schema artifact (e.g. to a JSON Schema or a UI columns view).
    """

    dtype: str
    """
    string | bool | int8..int64 / uint8..uint64 | float16/32/64 | struct | list |
    messages | image | audio | video | json | ... — fixed-width numeric widths as
    the source file reports them.
    """

    fields: Optional[List["FeatureSchema"]] = None
    """dtype == struct: named child fields."""

    items: Optional["FeatureSchema"] = None
    """
    One node of the row schema, derived de novo from the data (there is no external
    JSON-Schema store to reference). Carries the measured layout (name, dtype,
    children) plus at most one detected `semantic_role` marker stacked on the same
    node.

    Recursive and fully expanded: a `struct` node has child `fields`; a `list` /
    `messages` node has an element `items` — for `messages` the per-message
    `{role, content}` struct is spelled out, so a vision message whose content is a
    list of typed parts shows up structurally. The column-level chat summary lives
    in `MessageStats` on the stats side. This tree is the clean, bridgeable schema
    artifact (e.g. to a JSON Schema or a UI columns view).
    """

    name: Optional[str] = None
    """Column / struct-field name; "" for a list element."""

    semantic_role: Optional[str] = None
    """
    Detected role (from the role vocabulary), valid at any depth of the tree;
    omitted when nothing was detected. The only detected attribute in the structure
    layer — its evidence lands in PartitionClassification.evidence. Named
    `semantic_role`, not `role`, so it never collides with a message struct's `role`
    key.
    """

    semantic_role_source: Optional[str] = None
    """Where `semantic_role` came from: detected | declared.

    A declared role was supplied by the caller and only accepted because the dtype
    could carry it; a detected one was inferred from the column name. Kept as a
    field rather than left to evidence prose because the distinction is per-column
    and actionable — a UI renders a declared role as confirmed and a detected one as
    a suggestion to correct.
    """
