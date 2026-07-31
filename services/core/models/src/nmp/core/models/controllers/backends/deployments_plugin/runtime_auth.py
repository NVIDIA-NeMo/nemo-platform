# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Delegated authorization for model files downloaded by runtime pullers."""

from nemo_platform.types.inference.model_deployment import ModelDeployment
from nmp.common.auth import Principal, build_service_principal_bearer_token
from nmp.common.config import get_auth_config


def files_service_bearer_token(deployment: ModelDeployment, source_workspace: str) -> str:
    """Return an HF token that rechecks the deployment creator's current access."""
    auth_context = getattr(deployment, "auth_context", None)
    if auth_context is None:
        if not get_auth_config().enabled:
            return "service:models"
        raise ValueError(
            "Model downloads require a deployment auth context; "
            f"cannot access {source_workspace!r} from {deployment.workspace!r}"
        )

    principal = Principal(
        id=auth_context.principal_id,
        email=getattr(auth_context, "principal_email", None),
        # Durable runtime credentials must not replay creation-time group claims.
        groups=[],
        on_behalf_of=getattr(auth_context, "principal_on_behalf_of", None),
        on_behalf_of_email=getattr(auth_context, "principal_on_behalf_of_email", None),
        on_behalf_of_groups=None,
    )
    return build_service_principal_bearer_token(
        "models",
        on_behalf_of=principal,
        origin_workspace=getattr(auth_context, "origin_workspace", None) or deployment.workspace,
        source_workspace=source_workspace,
    )
