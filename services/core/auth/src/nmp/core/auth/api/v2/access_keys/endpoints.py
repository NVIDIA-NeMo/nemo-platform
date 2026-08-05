# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from nemo_platform_plugin.auth.access_keys.issuer import (
    AccessKeyFeatureDisabledError,
    AccessKeyOperationNotImplementedError,
)
from nmp.common.auth import AuthClient, get_auth_client
from nmp.common.config import get_auth_config
from nmp.core.auth.app.access_keys import (
    AccessKeyNotFoundError,
    AccessKeyRegistry,
    PersistentAccessKeyIssuer,
    get_access_key_registry,
)

from . import schemas

router = APIRouter(tags=["Scoped Access Keys"])

_ACCESS_KEY_DISABLED_ERROR_RESPONSE: dict[str, Any] = {
    "description": "Scoped Access Keys are not enabled",
    "model": schemas.AccessKeyErrorResponse,
}
_ACCESS_KEY_DISABLED_OR_NOT_FOUND_ERROR_RESPONSE: dict[str, Any] = {
    "description": "Scoped Access Keys are not enabled or the key was not found",
    "model": schemas.AccessKeyErrorResponse,
}
_ACCESS_KEY_NOT_IMPLEMENTED_ERROR_RESPONSE: dict[str, Any] = {
    "description": "Not Implemented",
    "model": schemas.AccessKeyNotImplementedErrorResponse,
}
_ACCESS_KEY_CREATE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "description": "Scoped Access Key creation error",
        "model": schemas.AccessKeyErrorResponse,
    },
    404: _ACCESS_KEY_DISABLED_ERROR_RESPONSE,
    501: _ACCESS_KEY_NOT_IMPLEMENTED_ERROR_RESPONSE,
}
_ACCESS_KEY_LIFECYCLE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: _ACCESS_KEY_DISABLED_ERROR_RESPONSE,
    501: _ACCESS_KEY_NOT_IMPLEMENTED_ERROR_RESPONSE,
}
_ACCESS_KEY_REVOKE_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: _ACCESS_KEY_DISABLED_OR_NOT_FOUND_ERROR_RESPONSE,
    501: _ACCESS_KEY_NOT_IMPLEMENTED_ERROR_RESPONSE,
}


def get_access_key_issuer(
    auth_client: AuthClient = Depends(get_auth_client),
    registry: AccessKeyRegistry = Depends(get_access_key_registry),
) -> PersistentAccessKeyIssuer:
    return PersistentAccessKeyIssuer(get_auth_config(), auth_client.principal, registry)


def _not_implemented(exc: AccessKeyOperationNotImplementedError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc))


def _disabled(exc: AccessKeyFeatureDisabledError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/v2/access-keys",
    response_model=schemas.AccessKeyCreateResponse,
    responses=_ACCESS_KEY_CREATE_ERROR_RESPONSES,
)
async def create_access_key(
    request: schemas.AccessKeyCreateRequest,
    issuer: PersistentAccessKeyIssuer = Depends(get_access_key_issuer),
) -> schemas.AccessKeyCreateResponse:
    try:
        return await issuer.create_async(request)
    except AccessKeyFeatureDisabledError as exc:
        raise _disabled(exc) from exc
    except AccessKeyOperationNotImplementedError as exc:
        raise _not_implemented(exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get(
    "/v2/access-keys",
    response_model=schemas.AccessKeyListResponse,
    responses=_ACCESS_KEY_LIFECYCLE_ERROR_RESPONSES,
)
async def list_access_keys(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    issuer: PersistentAccessKeyIssuer = Depends(get_access_key_issuer),
) -> schemas.AccessKeyListResponse:
    try:
        return await issuer.list_async(page=page, page_size=page_size)
    except AccessKeyFeatureDisabledError as exc:
        raise _disabled(exc) from exc
    except AccessKeyOperationNotImplementedError as exc:
        raise _not_implemented(exc) from exc


@router.delete(
    "/v2/access-keys/{jti}",
    response_model=schemas.AccessKeyRevokeResponse,
    responses=_ACCESS_KEY_REVOKE_ERROR_RESPONSES,
)
async def revoke_access_key(
    jti: str,
    issuer: PersistentAccessKeyIssuer = Depends(get_access_key_issuer),
) -> schemas.AccessKeyRevokeResponse:
    try:
        revoked = await issuer.revoke_async(jti)
    except AccessKeyFeatureDisabledError as exc:
        raise _disabled(exc) from exc
    except AccessKeyOperationNotImplementedError as exc:
        raise _not_implemented(exc) from exc
    except AccessKeyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return schemas.AccessKeyRevokeResponse(jti=jti, revoked=revoked)
