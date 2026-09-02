# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Symmetric encryption + fingerprinting for BYOK credential payloads.

v0 uses a single Fernet key (AES-128-CBC + HMAC) from settings. The richer
envelope-encryption scheme in docs/API.md § Security is deferred; this module
is the single seam to swap in a KMS-backed data key when that lands.
"""

import hashlib

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from scaled_evals.api.settings import settings


def _fernets() -> list[Fernet]:
    keys = [settings.credentials_encryption_key]
    keys.extend(key.strip() for key in settings.credentials_encryption_key_previous.split(",") if key.strip())
    try:
        return [Fernet(key.encode()) for key in keys]
    except (TypeError, ValueError) as exc:
        raise RuntimeError("invalid credential encryption key configuration") from exc


def encrypt(plaintext: str) -> bytes:
    """Encrypt a credential payload for storage at rest."""
    return _fernets()[0].encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    """Decrypt a stored payload. Used only at dispatch, never on read paths."""
    ciphertext = bytes(token)
    for fernet in _fernets():
        try:
            return fernet.decrypt(ciphertext).decode()
        except InvalidToken:
            continue
    raise InvalidToken


def reencrypt(token: bytes) -> bytes:
    """Re-encrypt a payload with the primary key, accepting configured old keys."""
    return MultiFernet(_fernets()).rotate(bytes(token))


def fingerprint(plaintext: str) -> str:
    """Non-reversible short digest so callers can identify a loaded secret
    without exposing it. Stable across rotations of the same value."""
    return "sha256:" + hashlib.sha256(plaintext.encode()).hexdigest()[:16]
