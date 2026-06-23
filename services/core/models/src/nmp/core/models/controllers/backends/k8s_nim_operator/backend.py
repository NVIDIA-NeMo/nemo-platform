# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes NIM Operator backend implementation for Models Controller service.

This ``ServiceBackend`` owns the ``nemo_platform`` SDK, determines the state of
the *API object* (ModelDeployment / ModelDeploymentConfig), resolves every input
a reconciler needs (weight source, resource names, Files endpoint) into a
:class:`ResolvedDeployment`, selects the correct reconciler by engine, and
delegates. It holds NO Kubernetes-reconciliation logic itself -- that lives in
the two reconcilers under :mod:`.reconcilers`:

* :class:`NimOperatorReconciler` -- emits ``NIMService`` / ``NIMCache`` CRs.
* :class:`K8sReconciler` -- emits native Kubernetes objects directly (vLLM).
"""

import os
from logging import getLogger
from typing import Optional
from urllib.parse import urljoin

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import get_platform_config
from nmp.core.models.app import (
    get_deployment_resource_name,
    get_model_weights_type,
    get_nimcache_resource_name,
    parse_model_name_revision,
)
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.common import (
    DeploymentConfigView,
    deployment_config_view,
    deployment_elapsed_seconds,
)
from nmp.core.models.controllers.backends.engine import ENGINE_GENERIC, ENGINE_VLLM, config_engine
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.base import Reconciler, ResolvedDeployment
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.k8s import K8sReconciler
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.nim_operator import (
    NimOperatorReconciler,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.resource_deleter import ResourceDeleter
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.status_projector import StatusProjector
from nmp.core.models.controllers.context import ModelContext

logger = getLogger(__name__)


class K8sNimOperatorServiceBackend(ServiceBackend):
    """Kubernetes backend for managing model deployments.

    Resolves API-object state and delegates reconciliation to the engine-specific
    reconciler (NIM operator CRs vs. native Kubernetes objects).
    """

    def __init__(self, nmp_sdk, config, huggingface_model_puller: str):
        self._k8s_client: k8s_client.ApiClient | None = None
        self._dynamic_client: DynamicClient | None = None
        self._k8s_namespace: str | None = None
        self._backend_config: K8sNimOperatorConfig | None = None
        self._huggingface_model_puller = huggingface_model_puller
        self._status_projector: StatusProjector | None = None
        self._resource_deleter: ResourceDeleter | None = None
        self._nim_reconciler: NimOperatorReconciler | None = None
        self._k8s_reconciler: K8sReconciler | None = None
        super().__init__(nmp_sdk, config)

    def init(self) -> None:
        """Initialize Kubernetes backend and build the engine reconcilers."""
        logger.info("Initializing Kubernetes NIM Operator service backend")

        self._backend_config = K8sNimOperatorConfig(**self._config)
        logger.debug(f"Backend config: {self._backend_config.model_dump()}")

        try:
            # Try in-cluster config first (for running inside k8s)
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes configuration")
        except k8s_config.ConfigException:
            # Fall back to kubeconfig (for local development)
            k8s_config.load_kube_config()
            logger.info("Loaded kubeconfig configuration")

        self._k8s_client = k8s_client.ApiClient()
        self._dynamic_client = DynamicClient(self._k8s_client)

        self._k8s_namespace = self._get_current_namespace()
        logger.info(f"Models controller will deploy models to namespace: {self._k8s_namespace}")

        # Shared collaborators composed into both reconcilers (and used directly
        # by the PENDING-timeout policy below).
        self._status_projector = StatusProjector(
            k8s_client_=self._k8s_client,
            backend_config=self._backend_config,
            k8s_namespace=self._k8s_namespace,
        )
        self._resource_deleter = ResourceDeleter(k8s_namespace=self._k8s_namespace)

        self._nim_reconciler = NimOperatorReconciler(
            dynamic_client=self._dynamic_client,
            backend_config=self._backend_config,
            k8s_namespace=self._k8s_namespace,
            huggingface_model_puller=self._huggingface_model_puller,
            status=self._status_projector,
            deleter=self._resource_deleter,
        )
        self._k8s_reconciler = K8sReconciler(
            k8s_client_=self._k8s_client,
            backend_config=self._backend_config,
            k8s_namespace=self._k8s_namespace,
            huggingface_model_puller=self._huggingface_model_puller,
            status=self._status_projector,
            deleter=self._resource_deleter,
        )

    def shutdown(self) -> None:
        """Shutdown Kubernetes backend and release resources."""
        logger.info("Shutting down Kubernetes NIM Operator service backend")
        if self._k8s_client is not None:
            try:
                self._k8s_client.close()
                logger.debug("Kubernetes API client closed")
            except Exception as e:
                logger.warning(f"Error closing Kubernetes API client: {e}")

    def _get_current_namespace(self) -> str:
        """Get the Kubernetes namespace where the controller is running."""
        if self._backend_config and self._backend_config.namespace:
            return self._backend_config.namespace

        # Try to read from the service account namespace file (in-cluster)
        namespace_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
        if os.path.exists(namespace_file):
            with open(namespace_file, "r") as f:
                return f.read().strip()

        logger.warning("Could not determine k8s namespace, using 'default'")
        return "default"

    # ------------------------------------------------------------------
    # Name + weight-source resolution (API-object work owned by the backend)
    # ------------------------------------------------------------------

    def _get_resource_name(self, deployment: ModelDeployment) -> str:
        """Generate the k8s resource name for NIMService/PVC resources (63-char limit)."""
        return get_deployment_resource_name(deployment.workspace, deployment.name)

    def _get_nimcache_resource_name(self, deployment: ModelDeployment) -> str:
        """Generate the k8s resource name for NIMCache resources (59-char limit).

        NIMCache names are capped at 59 characters instead of 63 because
        k8s-nim-operator appends '-job' (4 chars) when creating its internal
        batch Job, and the resulting name must not exceed the 63-char K8s
        label limit.
        """
        return get_nimcache_resource_name(deployment.workspace, deployment.name)

    def _resolve_model_source(
        self,
        model_entity: Optional[ModelEntity],
        nim_config: DeploymentConfigView,
    ) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Derive the model namespace/name for NIMCache from the model entity's fileset.

        The HF-compatible Files API resolves models by *fileset* name, not by
        model-entity name.  When a model entity carries a fileset reference
        (e.g. ``hf://workspace/fileset`` or ``fileset://workspace/fileset``),
        the NIMCache source must use that fileset path so the model puller can
        actually find the files.  Falls back to ``nim_config`` fields when no
        fileset is available
        """
        model_namespace, model_name, model_revision = parse_model_name_revision(
            model_namespace=nim_config.model_namespace,
            model_name=nim_config.model_name,
            model_revision=nim_config.model_revision,
        )

        if model_entity and model_entity.fileset:
            fileset_path = str(model_entity.fileset).removeprefix("hf://").removeprefix("fileset://")
            parts = fileset_path.split("/", 1)
            if len(parts) == 2:
                logger.info(f"Resolved model source from entity fileset: namespace={parts[0]}, name={parts[1]}")
                return parts[0], parts[1], model_revision
            logger.warning(
                f"model_entity.fileset '{model_entity.fileset}' does not contain namespace/name, falling back to nim_config"
            )

        return model_namespace, model_name, model_revision

    def _remote_files_hf_url(self) -> str:
        """Cluster-routable Files HF endpoint for the puller Job.

        ``_get_files_hf_url`` resolves via the platform config's local-service
        routing, which returns ``localhost`` when the Files service runs in this
        same process. The puller is a *separate pod* and cannot reach localhost, so
        we resolve the Files URL from ``service_discovery``/``base_url`` directly
        (the cluster-routable address) and append the HF-compatible path.
        """
        platform_config = get_platform_config()
        files_url = platform_config.service_discovery.get("files") or platform_config.base_url
        return urljoin(files_url.rstrip("/") + "/", "apis/files/v2/hf")

    def _resolve(self, ctx: ModelContext) -> ResolvedDeployment:
        """Resolve everything a reconciler needs from the API object + SDK state."""
        deployment = ctx.model_deployment
        config = ctx.model_deployment_config
        model_entity = ctx.model_entity
        view = deployment_config_view(config)
        model_namespace, model_name, model_revision = self._resolve_model_source(model_entity, view)
        weights_type = get_model_weights_type(
            model_deployment=deployment,
            model_deployment_config=config,
            model_entity=model_entity,
        )
        return ResolvedDeployment(
            deployment=deployment,
            config=config,
            model_entity=model_entity,
            view=view,
            resource_name=self._get_resource_name(deployment),
            nimcache_resource_name=self._get_nimcache_resource_name(deployment),
            weights_type=weights_type,
            model_namespace=model_namespace,
            model_name=model_name,
            model_revision=model_revision,
            files_hf_url=self._remote_files_hf_url(),
            huggingface_model_puller=self._huggingface_model_puller,
        )

    def _select_reconciler(self, engine: str) -> Optional[Reconciler]:
        """Select the reconciler for an engine.

        Returns the vLLM reconciler for ``vllm``, the NIM-operator reconciler for
        any other engine (the default), and ``None`` for ``generic`` -- which the
        callers treat as the "unsupported engine" rejection (see
        :meth:`_unsupported_engine`).
        """
        if engine == ENGINE_VLLM:
            return self._k8s_reconciler
        if engine == ENGINE_GENERIC:
            return None
        return self._nim_reconciler

    @staticmethod
    def _unsupported_engine(engine: str) -> DeploymentStatusUpdate:
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message="The 'generic' engine is not yet supported on the k8s backend.",
            error_details={"error": "unsupported_engine", "engine": engine},
            host_url=None,
        )

    # ------------------------------------------------------------------
    # ServiceBackend interface (resolve + select + delegate)
    # ------------------------------------------------------------------

    async def create_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Create a new model deployment (dispatches on the config's engine)."""
        engine = config_engine(ctx.model_deployment_config)
        reconciler = self._select_reconciler(engine)
        if reconciler is None:
            return self._unsupported_engine(engine)
        resolved = self._resolve(ctx)
        return await reconciler.create(resolved)

    async def update_model_deployment(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Update an existing model deployment (dispatches on the config's engine)."""
        engine = config_engine(ctx.model_deployment_config)
        reconciler = self._select_reconciler(engine)
        if reconciler is None:
            return self._unsupported_engine(engine)
        resolved = self._resolve(ctx)
        return await reconciler.update(resolved)

    async def get_model_deployment_status(self, ctx: ModelContext) -> DeploymentStatusUpdate:
        """Get the current status of a model deployment.

        The engine is taken from the config (same selection as create/update), so a
        config is required. When ``ctx.model_deployment_config`` is ``None`` (e.g.
        the controller failed to fetch it this cycle) the backend cannot determine
        the deployment's state and returns ``UNKNOWN``; the controller retries on
        the next poll (which normally has a config) and escalates to ERROR after
        its retry budget.

        In addition to the reconciler's status, this method enforces the PENDING
        timeout policy: if the deployment has been alive longer than
        ``pending_timeout_seconds`` and is still PENDING, transition to ERROR with
        diagnostic information. (Crash-loop detection is handled inside the
        reconciler's pod drill-down.)
        """
        deployment = ctx.model_deployment
        config = ctx.model_deployment_config
        logger.debug(
            f"Checking deployment status: {deployment.workspace}/{deployment.name} "
            f"(version: {deployment.entity_version})"
        )

        if config is None:
            logger.warning(
                f"No config available for {deployment.workspace}/{deployment.name}; cannot determine status this cycle"
            )
            return DeploymentStatusUpdate(
                status="UNKNOWN",
                status_message="Deployment config unavailable; will retry.",
                host_url=None,
            )

        try:
            resource_name = self._get_resource_name(deployment)

            engine = config_engine(config)
            reconciler = self._select_reconciler(engine)
            if reconciler is None:
                return self._unsupported_engine(engine)
            # A reconciler MAY advance creation in get_status; it needs the
            # resolved config to compile the serving spec.
            resolved = self._resolve(ctx)
            result = await reconciler.get_status(resolved)

            if result.status == "PENDING":
                elapsed = deployment_elapsed_seconds(deployment)

                if elapsed >= self._backend_config.pending_timeout_seconds:
                    pod_name = self._status_projector.find_pod_name(resource_name)
                    return self._status_projector.build_pending_timeout_error(resource_name, elapsed, pod_name)

                # Use a stable message (no elapsed/timeout) so we don't create a new history entry every poll

            return result
        except Exception as e:
            logger.error(f"Failed to get status for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Unable to determine deployment status due to a service backend error",
                host_url=None,
            )

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete a model deployment by workspace and name (model deployment ID).

        Delete has only workspace/name (no config/engine -- it is also called for
        orphan reconciliation), so BOTH reconcilers are asked to delete the
        resources they own (NIMService/NIMCache CRs and the directly-emitted vLLM
        objects). Each delete is independent and 404-tolerant; one reconciler's
        failure never aborts the other. Real (non-404) failures are aggregated and
        surfaced as ERROR so we never report DELETED while cluster resources may
        remain.
        """
        logger.info(f"Deleting model deployment: {workspace}/{name}")
        return await self._delete_resources_by_model_deployment_id(workspace, name)

    async def _delete_resources_by_model_deployment_id(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Aggregate both reconcilers' deletes into a single status update."""
        errors: list[str] = []
        for result in (
            await self._nim_reconciler.delete(workspace, name),
            await self._k8s_reconciler.delete(workspace, name),
        ):
            if result.status == "ERROR" and result.error_details:
                errors.extend(result.error_details.get("errors", []))

        if errors:
            summary = "; ".join(errors)
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to fully delete deployment {workspace}/{name}: {summary}",
                error_details={"errors": errors},
                host_url=None,
            )
        return DeploymentStatusUpdate(
            status="DELETED",
            status_message="Deployment deletion initiated successfully",
            host_url=None,
        )

    async def list_managed_deployment_names(self) -> list[str]:
        """List deployment names (workspace/name) the backend manages.

        Unions the operator path (NIMServices) and the directly-emitted vLLM path
        (raw Deployments), both labelled by the same managed-by + workspace/name
        labels, for orphan reconciliation.
        """
        seen: set[str] = set()
        seen.update(await self._nim_reconciler.list_managed_deployment_names())
        seen.update(await self._k8s_reconciler.list_managed_deployment_names())
        return sorted(seen)
