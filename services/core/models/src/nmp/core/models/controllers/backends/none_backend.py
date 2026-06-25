# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""None service backend."""

from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.context import ModelContext


class NoneServiceBackend(ServiceBackend):
    """None service backend."""

    def init(self) -> None:
        """Initialize None service backend."""
        ...

    def shutdown(self) -> None:
        """Shutdown None service backend."""
        ...

    async def create_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Create a new model deployment."""
        raise NotImplementedError("NoneServiceBackend does not support deployments")

    async def update_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Update a model deployment."""
        raise NotImplementedError("NoneServiceBackend does not support deployments")

    async def get_model_deployment_status(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Get the status of a model deployment."""
        return DeploymentStatusUpdate(
            status="UNKNOWN",
            status_message="NoneServiceBackend does not support deployments",
            error_details={"error": "NoneServiceBackend does not support deployments"},
        )

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete a model deployment."""
        raise NotImplementedError("NoneServiceBackend does not support deployments")

    async def list_managed_deployment_names(self) -> list[str]:
        """Return an empty list — NoneServiceBackend manages no deployments.

        The orphan-reconciliation loop calls this to find deployments the
        backend owns. The ``none`` backend can't own any, so it has nothing
        to report.
        """
        return []
