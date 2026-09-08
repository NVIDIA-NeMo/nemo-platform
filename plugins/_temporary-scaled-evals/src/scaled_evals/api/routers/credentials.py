# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from scaled_evals.api import crypto
from scaled_evals.api.auth import CurrentPrincipal, current_principal
from scaled_evals.api.credential_verification import (
    CredentialVerificationFailed,
    CredentialVerificationUnavailable,
    verify_stored_credential,
)
from scaled_evals.api.db import Database, get_db
from scaled_evals.api.repositories.base_repository import Conflict
from scaled_evals.api.schemas.common import DeleteResponse, ListEnvelope, page_from_rows
from scaled_evals.api.schemas.credentials import (
    Credential as CredentialSchema,
)
from scaled_evals.api.schemas.credentials import (
    CredentialCreate,
    CredentialCreateResponse,
    CredentialProvider,
    CredentialRename,
    CredentialRotate,
    CredentialVerifyResponse,
)
from scaled_evals.api.tenancy import is_admin, record_principal
from scaled_evals.api.utils import make_id

router = APIRouter(prefix="/credentials", tags=["credentials"])

Db = Annotated[Database, Depends(get_db)]
Principal = Annotated[CurrentPrincipal, Depends(current_principal)]


def _include_unowned(current: CurrentPrincipal) -> bool:
    # Local auth-disabled development retains access to pre-ownership rows.
    # Hosted legacy rows are visible only to explicitly configured admins.
    return current.source == "disabled" or is_admin(current)


def _http_error(
    status: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": {"code": code, "message": message, "details": details or {}}},
    )


@router.post("", status_code=201, response_model=CredentialCreateResponse)
def create_credential(body: CredentialCreate, db: Db, current: Principal) -> CredentialCreateResponse:
    """Register a BYOK credential. The write-once `key` or `yaml` secret is
    encrypted at rest; the response carries metadata + `fingerprint` only.

    Input: `CredentialCreate`. `provider` states what the secret is for, and
    exactly one of `key`/`yaml` must be present.
    Output: `CredentialCreateResponse` — the stored row (metadata +
    `fingerprint`) plus `links` for follow-up calls (self, rotate).

    Errors: 422 on schema validation (unknown `provider`, or neither/both of
    `key`/`yaml`).
    """
    record_principal(db, current)
    cred_id = make_id("cred")
    row = db.credentials.create(
        cred_id,
        name=body.name,
        provider=body.provider,
        payload_kind=body.payload_kind,
        encrypted_payload=crypto.encrypt(body.payload),
        fingerprint=crypto.fingerprint(body.payload),
        owner_id=current.owner_id,
    )
    db.commit()
    return CredentialCreateResponse(
        **row,
        links={
            "self": f"/credentials/{cred_id}",
            "rotate": f"/credentials/{cred_id}/rotate",
        },
    )


@router.get("", response_model=ListEnvelope[CredentialSchema])
def list_credentials(
    db: Db,
    current: Principal,
    provider: CredentialProvider | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    q: str | None = Query(default=None, min_length=1, max_length=200),
) -> ListEnvelope[CredentialSchema]:
    """Paginated list of the caller's live credentials, newest first.

    Input: optional `?provider=` filter, `?limit=N` (1..100), `?cursor=`.
    Output: `ListEnvelope[Credential]` (metadata only) with `next_cursor`
    when more rows exist.
    """
    rows = db.credentials.list(
        provider=provider,
        limit=limit,
        cursor=cursor,
        order=order,
        owner_id=current.owner_id,
        include_unowned=_include_unowned(current),
        q=q,
    )
    return page_from_rows(rows, limit, CredentialSchema)


@router.get("/{credential_id}", response_model=CredentialSchema)
def get_credential(credential_id: str, db: Db, current: Principal) -> CredentialSchema:
    """Fetch credential metadata by id. 404 if not found or revoked.

    Output: `Credential` — `fingerprint` only, never the plaintext payload.
    """
    row = db.credentials.get_metadata(
        credential_id,
        owner_id=current.owner_id,
        include_unowned=_include_unowned(current),
    )
    if row is None:
        raise _http_error(404, "not_found", "credential not found")
    return CredentialSchema(**row)


@router.patch("/{credential_id}", response_model=CredentialSchema)
def patch_credential(credential_id: str, body: CredentialRename, db: Db, current: Principal) -> CredentialSchema:
    """Rename a credential. Only `name` is mutable — the payload and provider
    are fixed; use `/rotate` to replace the secret.

    Input: `CredentialRename` (just `name`).
    Output: the updated `Credential`.

    Errors: 404 if not found or revoked.
    """
    row = db.credentials.rename(
        credential_id,
        name=body.name,
        owner_id=current.owner_id,
        include_unowned=_include_unowned(current),
    )
    if row is None:
        raise _http_error(404, "not_found", "credential not found")
    return CredentialSchema(**row)


@router.post("/{credential_id}/rotate", response_model=CredentialSchema)
def rotate_credential(credential_id: str, body: CredentialRotate, db: Db, current: Principal) -> CredentialSchema:
    """Replace the encrypted payload in place, recomputing the fingerprint.

    Input: `CredentialRotate` — a new `key` or `yaml` (exactly one).
    Output: the updated `Credential` (new `fingerprint`, never the secret).

    Errors: 404 if not found or revoked; 422 if neither/both of `key`/`yaml`.
    """
    try:
        row = db.credentials.rotate(
            credential_id,
            payload_kind=body.payload_kind,
            encrypted_payload=crypto.encrypt(body.payload),
            fingerprint=crypto.fingerprint(body.payload),
            owner_id=current.owner_id,
            include_unowned=_include_unowned(current),
        )
    except Conflict as exc:
        raise _http_error(409, exc.code, exc.message) from exc
    if row is None:
        raise _http_error(404, "not_found", "credential not found")
    return CredentialSchema(**row)


@router.delete("/{credential_id}", status_code=200, response_model=DeleteResponse)
def delete_credential(credential_id: str, db: Db, current: Principal) -> DeleteResponse:
    """Revoke a credential (soft-delete).

    Output: `{"id", "deleted": true}`.
    Errors: 404 if not found or already revoked; 409 if an active evaluation
    still references it.
    """
    try:
        deleted = db.credentials.soft_delete(
            credential_id,
            owner_id=current.owner_id,
            include_unowned=_include_unowned(current),
        )
    except Conflict as exc:
        raise _http_error(409, exc.code, exc.message) from exc
    if not deleted:
        raise _http_error(404, "not_found", "credential not found")
    return DeleteResponse(id=credential_id)


@router.post("/{credential_id}/verify", status_code=200, response_model=CredentialVerifyResponse)
def verify_credential(credential_id: str, db: Db, current: Principal) -> CredentialVerifyResponse:
    """Optional upstream validation ping.

    Output: `{"id", "verified", "reason"}`. Model-provider credentials are
    decrypted only for this call and probed against low-cost upstream metadata
    endpoints. Plaintext never appears in the response or error body.

    Errors: 404 if not found or revoked; 422 if the provider rejects the
    credential; 503 if the configured verification endpoint is unavailable.
    """
    row = db.credentials.get_secret_payload(
        credential_id,
        owner_id=current.owner_id,
        include_unowned=_include_unowned(current),
    )
    if row is None:
        raise _http_error(404, "not_found", "credential not found")

    provider = row["provider"]
    try:
        result = verify_stored_credential(row)
    except CredentialVerificationFailed as exc:
        raise _http_error(
            422,
            "credential_verify_failed",
            str(exc),
            {"provider": provider, "status_code": exc.status_code},
        ) from exc
    except CredentialVerificationUnavailable as exc:
        raise _http_error(
            503,
            "credential_verify_unavailable",
            str(exc),
            {"provider": provider},
        ) from exc

    return CredentialVerifyResponse(
        id=credential_id,
        verified=result.verified,
        reason=result.reason,
    )
