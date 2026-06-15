# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""NIM-operator reconciler: emits NIMService / NIMCache CRs.

This reconciler delegates the actual reconciliation to the in-cluster
k8s-nim-operator. It creates/updates/deletes ``NIMService`` and ``NIMCache``
custom resources and projects status by reading the operator-reported
``NIMService.status`` (drilling into the operator-created Deployment's pods when
the operator reports ``NotReady``).

The logic here is moved verbatim from the previous monolithic
``K8sNimOperatorServiceBackend``; the only change is that inputs arrive
pre-resolved on a :class:`ResolvedDeployment` (the ServiceBackend does the SDK /
entity-shaping work) instead of being recomputed here.
"""

from logging import getLogger

from kubernetes import client as k8s_client
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler import (
    compile_nimcache,
    compile_nimservice,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.reconcilers.base import (
    BaseReconciler,
    ResolvedDeployment,
)

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


class NimOperatorReconciler(BaseReconciler):
    """Reconciles a deployment by emitting NIMService / NIMCache CRs.

    Holds its own dynamic client (NIM CRDs are accessed via API discovery). Status
    is projected from the operator-reported ``NIMService.status``; when the
    operator reports ``NotReady`` it drills into the operator-created Deployment's
    pods using the shared :class:`BaseReconciler` helpers.
    """

    def __init__(
        self,
        k8s_client_: k8s_client.ApiClient,
        dynamic_client: DynamicClient,
        backend_config: K8sNimOperatorConfig,
        k8s_namespace: str,
        huggingface_model_puller: str,
    ) -> None:
        super().__init__(k8s_client_, backend_config, k8s_namespace)
        self._dynamic_client = dynamic_client
        self._huggingface_model_puller = huggingface_model_puller

    # ------------------------------------------------------------------
    # Reconciler interface
    # ------------------------------------------------------------------

    async def create(self, resolved: ResolvedDeployment) -> DeploymentStatusUpdate:
        deployment = resolved.deployment
        config = resolved.config
        model_entity = resolved.model_entity

        logger.info(
            f"Creating NIMService: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )

        # Check if Files service model (SFT or fileset) and create NIMCache if needed
        nimcache_name = None
        if resolved.weights_type == ModelWeightsType.FILES_SERVICE:
            logger.info(
                f"Files service model detected for deployment {deployment.workspace}/{deployment.name}, creating NIMCache"
            )

            view = resolved.view
            pvc_size = view.disk_size if view.disk_size else self._backend_config.default_pvc_size

            try:
                model_namespace = resolved.model_namespace
                model_name = resolved.model_name
                model_revision = resolved.model_revision

                if not model_namespace or not model_name:
                    logger.error(
                        f"Files service model detected but missing model namespace or name in config: "
                        f"namespace={model_namespace}, name={model_name}"
                    )
                    return DeploymentStatusUpdate(
                        status="ERROR",
                        status_message="Cannot create NIMCache for Files service model: missing model namespace or name in configuration",
                        error_details={
                            "error": "Missing required model namespace or name for Files service model",
                            "model_namespace": model_namespace,
                            "model_name": model_name,
                        },
                        host_url=None,
                    )

                nimcache_resource_name = resolved.nimcache_resource_name

                nimcache = compile_nimcache(
                    backend_config=self._backend_config,
                    k8s_namespace=self._k8s_namespace,
                    resource_name=nimcache_resource_name,
                    model_namespace=model_namespace,
                    model_name=model_name,
                    pvc_size=pvc_size,
                    huggingface_model_puller=self._huggingface_model_puller,
                    model_revision=model_revision,
                )

                await self._create_nimcache(nimcache)
                nimcache_name = nimcache_resource_name
                logger.info(f"NIMCache created successfully: {nimcache_name}")

            except Exception as e:
                logger.error(f"Failed to create NIMCache for Files service model: {e}")
                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=f"Failed to create NIMCache for Files service model: {str(e)}",
                    error_details={"error": str(e), "error_type": type(e).__name__},
                    host_url=None,
                )
        else:
            logger.debug(f"No Files service model detected for deployment {deployment.workspace}/{deployment.name}")

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
                    f"Successfully created NIMService {self._k8s_namespace}/{resource_name} "
                    f"with UID: {created.metadata.uid}"
                )
            except k8s_dynamic_exceptions.ConflictError:
                # NIMService already exists, just return PENDING and let status check handle it
                logger.info(f"NIMService {resource_name} already exists, skipping creation")

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="NIMService creation initiated successfully",
                host_url=self._get_host_url(resource_name),
            )

        except Exception as e:
            logger.error(f"Failed to create NIMService for {deployment.workspace}/{deployment.name}: {e}")
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
            f"Updating NIMService: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )

        # Check if Files service model (SFT or fileset) and create/update NIMCache if needed
        nimcache_name = None
        if resolved.weights_type == ModelWeightsType.FILES_SERVICE:
            logger.info(
                f"Files service model detected for deployment update {deployment.workspace}/{deployment.name}, creating/updating NIMCache"
            )

            view = resolved.view
            pvc_size = view.disk_size if view.disk_size else self._backend_config.default_pvc_size

            try:
                model_namespace = resolved.model_namespace
                model_name = resolved.model_name
                model_revision = resolved.model_revision

                if not model_namespace or not model_name:
                    logger.error(
                        f"Files service model detected but missing model namespace or name in config: "
                        f"namespace={model_namespace}, name={model_name}"
                    )
                    return DeploymentStatusUpdate(
                        status="ERROR",
                        status_message="Cannot create NIMCache for Files service model: missing model namespace or name in configuration",
                        error_details={
                            "error": "Missing required model namespace or name for Files service model",
                            "model_namespace": model_namespace,
                            "model_name": model_name,
                        },
                        host_url=None,
                    )

                nimcache_resource_name = resolved.nimcache_resource_name

                nimcache = compile_nimcache(
                    backend_config=self._backend_config,
                    k8s_namespace=self._k8s_namespace,
                    resource_name=nimcache_resource_name,
                    model_namespace=model_namespace,
                    model_name=model_name,
                    pvc_size=pvc_size,
                    huggingface_model_puller=self._huggingface_model_puller,
                    model_revision=model_revision,
                )

                await self._create_nimcache(nimcache)
                nimcache_name = nimcache_resource_name
                logger.info(f"NIMCache created/updated successfully: {nimcache_name}")

            except Exception as e:
                logger.error(f"Failed to create/update NIMCache for Files service model: {e}")
                return DeploymentStatusUpdate(
                    status="ERROR",
                    status_message=f"Failed to create/update NIMCache for Files service model: {str(e)}",
                    error_details={"error": str(e), "error_type": type(e).__name__},
                    host_url=None,
                )
        else:
            logger.debug(
                f"No Files service model detected for deployment update {deployment.workspace}/{deployment.name}"
            )

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
                f"Successfully updated NIMService {self._k8s_namespace}/{resource_name} "
                f"with UID: {updated.metadata.uid}"
            )

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="NIMService update initiated successfully",
                host_url=self._get_host_url(resource_name),
            )

        except k8s_dynamic_exceptions.NotFoundError:
            logger.warning(f"NIMService {resource_name} not found, treating as create operation")
            return await self.create(resolved)

        except Exception as e:
            logger.error(f"Failed to update NIMService for {deployment.workspace}/{deployment.name}: {e}")
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
        from nmp.core.models.app import get_deployment_resource_name, get_nimcache_resource_name

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
            err = self._delete_one(
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
            logger.warning(f"Failed to list NIMServices for orphan reconciliation: {e}")
        return sorted(seen)

    # ------------------------------------------------------------------
    # NIM-specific helpers (moved verbatim)
    # ------------------------------------------------------------------

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
                f"Successfully created NIMCache {self._k8s_namespace}/{nimcache.metadata['name']} "
                f"with UID: {created.metadata.uid}"
            )
        except k8s_dynamic_exceptions.ConflictError:
            logger.info(f"NIMCache {nimcache.metadata['name']} already exists, skipping creation")
        except Exception as e:
            logger.error(f"Failed to create NIMCache {nimcache.metadata['name']}: {e}")
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
                f"NIMService {resource_name} not found in cluster for deployment {resource_name}. "
                f"The resource may have been manually deleted or removed during namespace cleanup."
            )
            return DeploymentStatusUpdate(
                status="LOST",
                status_message="NIMService not found in cluster. Resource may have been deleted externally.",
                host_url=None,
            )

        nim_status = nimservice.get("status", {})
        state = nim_status.get("state", "").lower()

        match state:
            case "ready":
                return DeploymentStatusUpdate(
                    status="READY",
                    status_message="",
                    host_url=self._get_host_url(resource_name),
                )
            case "notready":
                conditions = nim_status.get("conditions", [])
                logger.info(f"NIMService {resource_name} is NotReady. Conditions: {conditions}")

                pod_status_result = self._get_pod_status_from_deployment(resource_name)

                return pod_status_result
            case "failed":
                conditions = nim_status.get("conditions", [])
                logger.error(f"NIMService {resource_name} has failed. Conditions: {conditions}")
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
