# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Shared request and query types for Inference Gateway VirtualModel CRUD.

The canonical VirtualModel response and nested middleware types remain in
``inference_middleware`` because middleware plugins already consume them. This
module re-exports those types alongside the CRUD request contract used by both
the Inference Gateway router and the typed client.

Entity-store filter models remain server-side. Clients pass the public filter
expression as a string through :class:`ListVirtualModelsQueryParams`.
"""

from __future__ import annotations

from typing import NotRequired, TypedDict

from nemo_platform_plugin.inference_middleware import (
    _AUTOPROVISIONED_DESC,
    MiddlewareCall,
    VirtualModel,
    VirtualModelInferenceConfig,
)
from pydantic import BaseModel, Field

__all__ = [
    "CreateVirtualModelRequest",
    "ListVirtualModelsQueryParams",
    "MiddlewareCall",
    "UpdateVirtualModelRequest",
    "VirtualModel",
    "VirtualModelInferenceConfig",
]


class _VirtualModelFields(BaseModel):
    """Mutable fields shared by create and update requests."""

    default_model_entity: str | None = Field(
        default=None,
        description=(
            'Model entity to route to, in "workspace/name" format. Written into request["model"] '
            "before the request middleware pipeline runs. If omitted, a request middleware plugin "
            "must handle backend routing itself. Set to null to clear an existing value."
        ),
    )
    autoprovisioned: bool = Field(
        default=False,
        description=_AUTOPROVISIONED_DESC,
    )
    models: list[VirtualModelInferenceConfig] = Field(
        default_factory=list,
        description=(
            "Model entity references used by this VirtualModel. A per-entry backend_format overrides the referenced "
            "ModelEntity backend_format when IGW resolves the backend format for a request."
        ),
    )
    request_middleware: list[MiddlewareCall] = Field(
        default_factory=list,
        description=(
            "Ordered list of middleware plugins applied before proxying to the backend. "
            'Each entry is a MiddlewareCall with required "name" (plugin identifier) and '
            '"config_type" fields, plus optional inline "config" or stored "config_id" configuration.'
        ),
    )
    response_middleware: list[MiddlewareCall] = Field(
        default_factory=list,
        description=(
            "Ordered list of middleware plugins applied after the backend response is received, "
            "before returning it to the caller."
        ),
    )
    post_response_middleware: list[MiddlewareCall] = Field(
        default_factory=list,
        description=(
            "Ordered list of middleware plugins invoked after the response has been returned to "
            "the caller. Intended for fire-and-forget work (logging, analytics) that must not "
            "block or modify the response."
        ),
    )
    override_proxy: str | None = Field(
        default=None,
        description=(
            "Plugin-provided proxy implementation for IGW to use instead of its default aiohttp proxy. "
            'Format: "plugin-name.proxy-name". Leave unset to use the default IGW proxy. '
            "Set to null to clear an existing value."
        ),
    )


class CreateVirtualModelRequest(_VirtualModelFields):
    """Request body for creating a VirtualModel."""

    name: str = Field(
        description="Name of the virtual model within the workspace. Must be unique per workspace.",
    )


class UpdateVirtualModelRequest(_VirtualModelFields):
    """Request body for partially updating a VirtualModel.

    Only explicitly set fields are serialized by the endpoint layer. Omitted
    fields retain their current values, while explicit nulls clear nullable
    fields.
    """


class ListVirtualModelsQueryParams(TypedDict, total=False):
    """Query parameters accepted by the VirtualModel list operation."""

    page: NotRequired[int]
    page_size: NotRequired[int]
    sort: NotRequired[str]
    filter: NotRequired[str]
    exclude_autoprovisioned: NotRequired[bool]
