# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reconciler interface + the pre-resolved inputs a reconciler operates on.

The k8s service backend splits responsibilities:

* ``K8sNimOperatorServiceBackend`` (the ``ServiceBackend``) owns the
  ``nemo_platform`` SDK, determines the current state of the *API object*
  (ModelDeployment / ModelDeploymentConfig), resolves all inputs a reconciler
  needs (weight source, resource names, Files endpoint), selects the correct
  reconciler by engine, and delegates.
* A ``Reconciler`` reconciles desired state (the API object) against the actual
  state of *backend infra resources*. It does NOT call the ``nemo_platform`` SDK
  and does NOT infer API-object state; it receives everything pre-resolved in a
  :class:`ResolvedDeployment` and talks only to the Kubernetes API.

Two reconcilers implement this interface:

* ``NimOperatorReconciler`` -- emits ``NIMService`` / ``NIMCache`` CRs and lets the
  in-cluster k8s-nim-operator do the actual reconciliation; status is propagated
  upward from the operator-created resources.
* ``K8sReconciler`` -- emits native Kubernetes objects directly (PVC / Job /
  Deployment / Service) and drives a staged rollout itself, advancing the
  deployment one phase at a time as it is polled via ``get_status``.

``Reconciler`` is a pure interface: shared read-side logic (status projection) and
delete semantics are *composed* in via :class:`StatusProjector` and
:class:`ResourceDeleter` rather than inherited, so each reconciler declares
exactly the collaborators it needs.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import DeploymentConfigView


@dataclass
class ResolvedDeployment:
    """Everything a reconciler needs, pre-resolved by the ServiceBackend.

    The ServiceBackend computes these (the SDK/entity-shaping and API-object work)
    and hands them to a reconciler so the reconciler can stay infra-only: it never
    calls the ``nemo_platform`` SDK and never re-derives names or the weight
    source. Fields not relevant to a given engine are simply left unset.
    """

    deployment: ModelDeployment
    config: ModelDeploymentConfig
    model_entity: Optional[ModelEntity]
    view: DeploymentConfigView

    # k8s resource name for the deployment (NIMService / vLLM Deployment / PVC).
    resource_name: str
    # k8s resource name for the NIMCache (NIM path only; reserves the "-job" suffix).
    nimcache_resource_name: str

    # Resolved weight source.
    weights_type: ModelWeightsType
    model_namespace: Optional[str] = None
    model_name: Optional[str] = None
    model_revision: Optional[str] = None

    # Cluster-routable Files HF endpoint for the in-cluster weight puller (vLLM).
    files_hf_url: Optional[str] = None
    # Image used to pull weights (NIMCache modelPuller / vLLM puller Job).
    huggingface_model_puller: Optional[str] = None


class Reconciler(ABC):
    """Reconciles desired deployment state against actual backend resources.

    Implementations talk only to Kubernetes. Shared status projection and delete
    semantics are composed in (see :class:`StatusProjector` /
    :class:`ResourceDeleter`), not inherited.
    """

    @abstractmethod
    async def create(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Reconcile toward the desired state for a newly-created deployment."""
        ...

    @abstractmethod
    async def update(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Reconcile toward the desired state for an updated deployment."""
        ...

    @abstractmethod
    async def get_status(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        """Project the actual state of backend resources into a status update.

        Reconcilers MAY advance creation here (the direct-emission reconciler
        drives its staged rollout from this method); the operator reconciler just
        reads operator-reported status.
        """
        ...

    @abstractmethod
    async def delete(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete the backend resources this reconciler owns (idempotent)."""
        ...

    @abstractmethod
    async def list_managed_deployment_names(self) -> list[str]:
        """List ``workspace/name`` for deployments this reconciler manages."""
        ...
