# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from nemo_platform_plugin.auth.access_keys.issuer import (
    AccessKeyFeatureDisabledError,
    AccessKeyIssuer,
    AccessKeyOperationNotImplementedError,
)
from nmp.common.auth import AuthClient, get_auth_client
from nmp.common.auth.access_keys import AccessKeyIssuerService
from nmp.common.config import get_auth_config

from . import schemas

router = APIRouter(tags=["Scoped Access Keys"])

_ACCESS_KEY_DISABLED_ERROR_RESPONSE: dict[str, Any] = {
    "description": "Scoped Access Keys are not enabled",
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


def get_access_key_issuer(auth_client: AuthClient = Depends(get_auth_client)) -> AccessKeyIssuerService:
    return AccessKeyIssuerService(config=get_auth_config(), principal=auth_client.principal)


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
    issuer: AccessKeyIssuerService = Depends(get_access_key_issuer),
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
async def list_access_keys(issuer: AccessKeyIssuer = Depends(get_access_key_issuer)) -> schemas.AccessKeyListResponse:
    try:
        return issuer.list()
    except AccessKeyFeatureDisabledError as exc:
        raise _disabled(exc) from exc
    except AccessKeyOperationNotImplementedError as exc:
        raise _not_implemented(exc) from exc


@router.delete("/v2/access-keys/{jti}", responses=_ACCESS_KEY_LIFECYCLE_ERROR_RESPONSES)
async def revoke_access_key(jti: str, issuer: AccessKeyIssuer = Depends(get_access_key_issuer)) -> None:
    try:
        issuer.revoke(jti)
    except AccessKeyFeatureDisabledError as exc:
        raise _disabled(exc) from exc
    except AccessKeyOperationNotImplementedError as exc:
        raise _not_implemented(exc) from exc
