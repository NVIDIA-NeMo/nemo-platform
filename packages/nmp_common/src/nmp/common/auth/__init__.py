# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Authentication and authorization utilities for NeMo Platform."""

from nmp.common.config import AuthConfig

from .access_keys import (
    ACCESS_KEY_JWKS_PATH,
    ACCESS_KEY_TOKEN_TYPE,
    AccessKeyIssuerService,
    validate_access_key_token,
)
from .client import AuthClient, AuthorizationResult
from .dependencies import (
    auth_as_service,
    auth_client_context,
    build_service_principal_headers,
    get_auth_client,
    get_principal_auth_headers,
)
from .exceptions import AuthorizationError, InvalidPermissionFormatError, InvalidScopeFormatError
from .middleware import AuthorizationMiddleware
from .models import NMP_PRINCIPAL_ENVVAR, AuthContext, Principal
from .permissions import ALL_WORKSPACES, compute_accessible_workspaces
from .tasks import principal_from_env
from .workload_delegations import (
    DOCKER_OPAQUE_WORKLOAD_PROOF_TOKEN_TYPE,
    JWT_WORKLOAD_SUBJECT_TOKEN_TYPE,
    KUBERNETES_POD_UID_REFERENCE_NAME,
    OPAQUE_DOCKER_PROOF_PREFIX,
    WORKLOAD_DELEGATION_ENTITY_TYPE,
    InvalidWorkloadProofTokenError,
    ParsedOpaqueDockerProofToken,
    SyncWorkloadDelegationStore,
    WorkloadDelegationConflictError,
    WorkloadDelegationEntity,
    WorkloadDelegationError,
    WorkloadDelegationStore,
    WorkloadDelegationValidationError,
    create_opaque_docker_proof_token,
    docker_delegation_name,
    parse_opaque_docker_proof_token,
    reference_delegation_name,
    subject_token_type_for_exchange,
    verify_opaque_docker_proof_token_hash,
)

# Testing utilities are NOT exported here to avoid importing dev dependencies (respx)
# at runtime. Import directly from nmp.common.auth.testing when needed in tests.

__all__ = [
    "ALL_WORKSPACES",
    "AuthClient",
    "AuthContext",
    "AuthConfig",
    "AuthorizationError",
    "InvalidPermissionFormatError",
    "InvalidScopeFormatError",
    "AuthorizationMiddleware",
    "AuthorizationResult",
    "ACCESS_KEY_JWKS_PATH",
    "ACCESS_KEY_TOKEN_TYPE",
    "AccessKeyIssuerService",
    "DOCKER_OPAQUE_WORKLOAD_PROOF_TOKEN_TYPE",
    "JWT_WORKLOAD_SUBJECT_TOKEN_TYPE",
    "KUBERNETES_POD_UID_REFERENCE_NAME",
    "OPAQUE_DOCKER_PROOF_PREFIX",
    "WORKLOAD_DELEGATION_ENTITY_TYPE",
    "InvalidWorkloadProofTokenError",
    "NMP_PRINCIPAL_ENVVAR",
    "ParsedOpaqueDockerProofToken",
    "Principal",
    "SyncWorkloadDelegationStore",
    "WorkloadDelegationConflictError",
    "WorkloadDelegationEntity",
    "WorkloadDelegationError",
    "WorkloadDelegationStore",
    "WorkloadDelegationValidationError",
    "auth_as_service",
    "auth_client_context",
    "build_service_principal_headers",
    "create_opaque_docker_proof_token",
    "docker_delegation_name",
    "principal_from_env",
    "parse_opaque_docker_proof_token",
    "reference_delegation_name",
    "subject_token_type_for_exchange",
    "compute_accessible_workspaces",
    "get_auth_client",
    "get_principal_auth_headers",
    "validate_access_key_token",
    "verify_opaque_docker_proof_token_hash",
]
