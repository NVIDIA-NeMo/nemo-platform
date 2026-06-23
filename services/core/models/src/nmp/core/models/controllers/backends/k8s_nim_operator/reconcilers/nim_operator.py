# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NIM-operator reconciler: emits NIMService / NIMCache CRs.

This reconciler delegates the actual reconciliation to the in-cluster
k8s-nim-operator. It creates/updates/deletes ``NIMService`` and ``NIMCache``
custom resources and projects status by reading the operator-reported
``NIMService.status`` (drilling into the operator-created Deployment's pods when
the operator reports ``NotReady``).

Inputs arrive pre-resolved on a :class:`ResolvedDeployment` (the ServiceBackend
does the SDK / entity-shaping work); this reconciler talks only to Kubernetes.
Shared status projection and delete semantics are composed in via
:class:`StatusProjector` and :class:`ResourceDeleter`.
"""

from logging import getLogger

from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nmp.core.models.app import (
    ModelWeightsType,
    get_deployment_resource_name,
    get_nimcache_resource_name,
)
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler import (
    compile_nimcache,
    compile_nimservice,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.base import (
    Reconciler,
    ResolvedDeployment,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.resource_deleter import ResourceDeleter
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.status_projector import StatusProjector

logger = getLogger(__name__)

NIM_OPERATOR_GROUP = "apps.nvidia.com"
NIMSERVICE_VERSION = "v1alpha1"
NIMSERVICE_API_VERSION = f"{NIM_OPERATOR_GROUP}/{NIMSERVICE_VERSION}"
NIMSERVICE_PLURAL = "nimservices"

NIMCACHE_VERSION = "v1alpha1"
NIMCACHE_API_VERSION = f"{NIM_OPERATOR_GROUP}/{NIMCACHE_VERSION}"
NIMCACHE_PLURAL = "nimcaches"

# Labels stamped by the NIMService compiler for orphan reconciliation.
NIMSERVICE_DEPLOYMENT_WORKSPACE_LABEL = "nmp.nvidia.com/deployment-workspace"
NIMSERVICE_DEPLOYMENT_NAME_LABEL = "nmp.nvidia.com/deployment-name"


class NimOperatorReconciler(Reconciler):
    """Reconciles a deployment by emitting NIMService / NIMCache CRs.

    Holds its own dynamic client (NIM CRDs are accessed via API discovery) and
    composes a :class:`StatusProjector` (for the operator-created Deployment's pod
    status when the operator reports ``NotReady``) and a :class:`ResourceDeleter`.
    """

    def __init__(
        self,
        dynamic_client: DynamicClient,
        backend_config: K8sNimOperatorConfig,
        k8s_namespace: str,
        huggingface_model_puller: str,
        status: StatusProjector,
        deleter: ResourceDeleter,
    ) -> None:
        self._dynamic_client = dynamic_client
        self._backend_config = backend_config
        self._k8s_namespace = k8s_namespace
        self._huggingface_model_puller = huggingface_model_puller
        self._status = status
        self._deleter = deleter

    # ------------------------------------------------------------------
    # Reconciler interface
    # ------------------------------------------------------------------

    async def create(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        deployment = resolved.deployment
        config = resolved.config
        model_entity = resolved.model_entity

        logger.info(
            "Creating NIMService",
            extra={
                "workspace": deployment.workspace,
                "deployment_name": deployment.name,
                "version": deployment.entity_version,
            },
        )

        # Check if Files service model (SFT or fileset) and create NIMCache if needed.
        nimcache_name, error = await self._ensure_nimcache(resolved, action="creating")
        if error is not None:
            return error

        try:
            resource_name = resolved.resource_name

            # Compile NIMService with optional NIMCache reference (env vars depend on nimcache_name + image type)
            nimservice = compile_nimservice(
                deployment=deployment,
                config=config,
                backend_config=self._backend_config,
                k8s_namespace=self._k8s_namespace,
                resource_name=resource_name,
                nimcache_name=nimcache_name,
                model_entity=model_entity,
                huggingface_model_puller=self._huggingface_model_puller,
            )

            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )

            nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

            try:
                created = nimservice_api.create(
                    body=nimservice_dict,
                    namespace=self._k8s_namespace,
                )
                logger.info(
                    "Successfully created NIMService",
                    extra={
                        "namespace": self._k8s_namespace,
                        "resource_name": resource_name,
                        "uid": created.metadata.uid,
                    },
                )
            except k8s_dynamic_exceptions.ConflictError:
                # NIMService already exists, just return PENDING and let status check handle it
                logger.info("NIMService already exists, skipping creation", extra={"resource_name": resource_name})

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="NIMService creation initiated successfully",
                host_url=self._status.host_url(resource_name),
            )

        except Exception as e:
            logger.error(
                "Failed to create NIMService",
                extra={"workspace": deployment.workspace, "deployment_name": deployment.name, "error": str(e)},
            )
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to create deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def update(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        deployment = resolved.deployment
        config = resolved.config
        model_entity = resolved.model_entity

        logger.info(
            "Updating NIMService",
            extra={
                "workspace": deployment.workspace,
                "deployment_name": deployment.name,
                "version": deployment.entity_version,
            },
        )

        # Check if Files service model (SFT or fileset) and create/update NIMCache if needed.
        nimcache_name, error = await self._ensure_nimcache(resolved, action="updating")
        if error is not None:
            return error

        try:
            resource_name = resolved.resource_name

            # Compile NIMService with optional NIMCache reference (env vars depend on nimcache_name + image type)
            nimservice = compile_nimservice(
                deployment=deployment,
                config=config,
                backend_config=self._backend_config,
                k8s_namespace=self._k8s_namespace,
                resource_name=resource_name,
                nimcache_name=nimcache_name,
                model_entity=model_entity,
                huggingface_model_puller=self._huggingface_model_puller,
            )

            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )

            nimservice_dict = nimservice.model_dump(exclude_none=True, by_alias=True)

            updated = nimservice_api.replace(
                body=nimservice_dict,
                name=resource_name,
                namespace=self._k8s_namespace,
            )

            logger.info(
                "Successfully updated NIMService",
                extra={"namespace": self._k8s_namespace, "resource_name": resource_name, "uid": updated.metadata.uid},
            )

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="NIMService update initiated successfully",
                host_url=self._status.host_url(resource_name),
            )

        except k8s_dynamic_exceptions.NotFoundError:
            logger.warning(
                "NIMService not found, treating as create operation", extra={"resource_name": resolved.resource_name}
            )
            return await self.create(resolved)

        except Exception as e:
            logger.error(
                "Failed to update NIMService",
                extra={"workspace": deployment.workspace, "deployment_name": deployment.name, "error": str(e)},
            )
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to update deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def get_status(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        return self._get_nimservice_status(resolved.resource_name)

    async def delete(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete the NIMService / NIMCache CRs this reconciler owns (idempotent).

        Returns an aggregated update; the ServiceBackend combines this with the
        other reconciler's delete result.
        """
        nimservice_name = get_deployment_resource_name(workspace, name)
        nimcache_name = get_nimcache_resource_name(workspace, name)
        errors: list[str] = []

        for api_version, kind, cr_name in (
            (NIMSERVICE_API_VERSION, "NIMService", nimservice_name),
            (NIMCACHE_API_VERSION, "NIMCache", nimcache_name),
        ):
            try:
                cr_api = self._dynamic_client.resources.get(api_version=api_version, kind=kind)
            except Exception as e:
                errors.append(f"error resolving {kind} API: {e}")
                continue
            err = self._deleter.delete_one(
                lambda name, namespace, _api=cr_api: _api.delete(name=name, namespace=namespace),
                kind,
                cr_name,
            )
            if err:
                errors.append(err)

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
        """List ``workspace/name`` for NIMServices this reconciler manages."""
        label_selector = f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}"
        seen: set[str] = set()
        try:
            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )
            result = nimservice_api.get(namespace=self._k8s_namespace, label_selector=label_selector)
            for item in getattr(result, "items", None) or []:
                labels = getattr(getattr(item, "metadata", None), "labels", None) or {}
                if isinstance(labels, dict):
                    workspace = labels.get(NIMSERVICE_DEPLOYMENT_WORKSPACE_LABEL)
                    name = labels.get(NIMSERVICE_DEPLOYMENT_NAME_LABEL)
                    if workspace and name:
                        seen.add(f"{workspace}/{name}")
        except k8s_dynamic_exceptions.ForbiddenError:
            # No RBAC for the NIM CRDs (e.g. a vLLM-only deployment). Not an error.
            logger.debug("No access to NIMServices for orphan reconciliation; skipping NIM path")
        except Exception as e:
            logger.warning("Failed to list NIMServices for orphan reconciliation", extra={"error": str(e)})
        return sorted(seen)

    # ------------------------------------------------------------------
    # NIM-specific helpers
    # ------------------------------------------------------------------

    async def _ensure_nimcache(
        self, resolved: ResolvedDeployment, action: str
    ) -> tuple[str | None, DeploymentStatusUpdate | None]:
        """Create the NIMCache for a Files-service model, if applicable.

        Returns ``(nimcache_name, None)`` on success (``nimcache_name`` is ``None``
        when the model is not a Files-service model), or ``(None, error_update)``
        when NIMCache creation should abort the create/update.
        """
        deployment = resolved.deployment

        if resolved.weights_type != ModelWeightsType.FILES_SERVICE:
            logger.debug(
                "No Files service model detected",
                extra={"workspace": deployment.workspace, "deployment_name": deployment.name, "action": action},
            )
            return None, None

        logger.info(
            "Files service model detected, creating NIMCache",
            extra={"workspace": deployment.workspace, "deployment_name": deployment.name, "action": action},
        )

        model_namespace = resolved.model_namespace
        model_name = resolved.model_name
        if not model_namespace or not model_name:
            logger.error(
                "Files service model detected but missing model namespace or name in config",
                extra={"model_namespace": model_namespace, "model_name": model_name},
            )
            return None, DeploymentStatusUpdate(
                status="ERROR",
                status_message="Cannot create NIMCache for Files service model: missing model namespace or name in configuration",
                error_details={
                    "error": "Missing required model namespace or name for Files service model",
                    "model_namespace": model_namespace,
                    "model_name": model_name,
                },
                host_url=None,
            )

        view = resolved.view
        pvc_size = view.disk_size if view.disk_size else self._backend_config.default_pvc_size

        try:
            nimcache = compile_nimcache(
                backend_config=self._backend_config,
                k8s_namespace=self._k8s_namespace,
                resource_name=resolved.nimcache_resource_name,
                model_namespace=model_namespace,
                model_name=model_name,
                pvc_size=pvc_size,
                huggingface_model_puller=self._huggingface_model_puller,
                model_revision=resolved.model_revision,
            )
            await self._create_nimcache(nimcache)
            logger.info("NIMCache created successfully", extra={"resource_name": resolved.nimcache_resource_name})
            return resolved.nimcache_resource_name, None
        except Exception as e:
            logger.error("Failed to create NIMCache for Files service model", extra={"error": str(e)})
            return None, DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to create NIMCache for Files service model: {str(e)}",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def _create_nimcache(self, nimcache) -> None:
        """Create a NIMCache CR in Kubernetes.

        Args:
            nimcache: The NIMCache CR to create
        """
        try:
            nimcache_api = self._dynamic_client.resources.get(
                api_version=NIMCACHE_API_VERSION,
                kind="NIMCache",
            )

            nimcache_dict = nimcache.model_dump(exclude_none=True, by_alias=True)

            created = nimcache_api.create(
                body=nimcache_dict,
                namespace=self._k8s_namespace,
            )
            logger.info(
                "Successfully created NIMCache",
                extra={
                    "namespace": self._k8s_namespace,
                    "resource_name": nimcache.metadata["name"],
                    "uid": created.metadata.uid,
                },
            )
        except k8s_dynamic_exceptions.ConflictError:
            logger.info(
                "NIMCache already exists, skipping creation", extra={"resource_name": nimcache.metadata["name"]}
            )
        except Exception as e:
            logger.error(
                "Failed to create NIMCache", extra={"resource_name": nimcache.metadata["name"], "error": str(e)}
            )
            raise

    def _get_nimservice_status(self, resource_name: str) -> DeploymentStatusUpdate:
        nimservice_api = self._dynamic_client.resources.get(
            api_version=NIMSERVICE_API_VERSION,
            kind="NIMService",
        )

        try:
            nimservice = nimservice_api.get(name=resource_name, namespace=self._k8s_namespace)
        except k8s_dynamic_exceptions.NotFoundError:
            logger.warning(
                "NIMService not found in cluster; may have been deleted externally",
                extra={"resource_name": resource_name},
            )
            return DeploymentStatusUpdate(
                status="LOST",
                status_message="NIMService not found in cluster. Resource may have been deleted externally.",
                host_url=None,
            )

        # ``status`` / ``status.state`` may be absent or explicitly null while the
        # operator is still populating them -- coerce to "" so .lower() is safe.
        nim_status = nimservice.get("status") or {}
        state = (nim_status.get("state") or "").lower()

        match state:
            case "ready":
                return DeploymentStatusUpdate(
                    status="READY",
                    status_message="",
                    host_url=self._status.host_url(resource_name),
                )
            case "notready":
                conditions = nim_status.get("conditions", [])
                logger.info("NIMService is NotReady", extra={"resource_name": resource_name, "conditions": conditions})
                return self._status.pod_status_from_deployment(resource_name)
            case "failed":
                conditions = nim_status.get("conditions", [])
                logger.error("NIMService has failed", extra={"resource_name": resource_name, "conditions": conditions})
                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=f"NIMService failed: {conditions}",
                    host_url=None,
                )
            case _:
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message=f"NIMService in {state or 'unknown'} state",
                    host_url=None,
                )
