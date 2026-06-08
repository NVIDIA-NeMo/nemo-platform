# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Custom exceptions for entity repository operations."""


class EntityRepositoryError(Exception):
    """Base exception for entity repository errors."""

    pass


class EntityNotFoundError(EntityRepositoryError):
    """Raised when an entity is not found."""

    pass


class EntityVersionConflictError(EntityRepositoryError):
    """Raised when entity version doesn't match (optimistic locking conflict)."""

    pass


class EntityAlreadyExistsError(EntityRepositoryError):
    """Raised when creating an entity that violates a uniqueness constraint.

    Translated from the backend's native integrity error so callers can map it
    to a 409 without sniffing driver-specific error strings.
    """

    pass
