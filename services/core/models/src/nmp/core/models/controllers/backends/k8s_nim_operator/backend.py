# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes NIM Operator backend implementation for Models Controller service."""

import os
from logging import getLogger
from typing import Any, Dict, Optional

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.core.models.app import (
    ModelWeightsType,
    get_deployment_resource_name,
    get_model_weights_type,
    get_nimcache_resource_name,
    parse_model_name_revision,
)
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.common import (
    LOG_MAX_CHARS,
    LOG_TAIL_LINES,
    deployment_config_view,
    deployment_elapsed_seconds,
    format_duration,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig
from nmp.core.models.controllers.backends.k8s_nim_operator.nimservice_compiler import (
    compile_nimcache,
    compile_nimservice,
)

logger = getLogger(__name__)

NIM_OPERATOR_GROUP = "apps.nvidia.com"
NIMSERVICE_VERSION = "v1alpha1"
NIMSERVICE_API_VERSION = f"{NIM_OPERATOR_GROUP}/{NIMSERVICE_VERSION}"
NIMSERVICE_PLURAL = "nimservices"

NIMCACHE_VERSION = "v1alpha1"
NIMCACHE_API_VERSION = f"{NIM_OPERATOR_GROUP}/{NIMCACHE_VERSION}"
NIMCACHE_PLURAL = "nimcaches"

POD_EVENT_TO_MESSAGE_MAP = {
    "startup probe failed": "Waiting for pod to finish startup",
}


class K8sNimOperatorServiceBackend(ServiceBackend):
    """Kubernetes NIM Operator backend for managing model deployments.

    Manages ModelDeployment lifecycle by creating and managing NIMService
    custom resources via the NIM Operator in Kubernetes.
    """

    def __init__(self, nmp_sdk, config, huggingface_model_puller: str):
        self._k8s_client: k8s_client.ApiClient | None = None
        self._dynamic_client: DynamicClient | None = None
        self._k8s_namespace: str | None = None
        self._backend_config: K8sNimOperatorConfig | None = None
        self._huggingface_model_puller = huggingface_model_puller
        super().__init__(nmp_sdk, config)

    def init(self) -> None:
        """Initialize Kubernetes NIM Operator backend."""
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

        self._validate_nim_operator_crds()

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

    def _validate_nim_operator_crds(self) -> None:
        """
        Validate that NIM Operator APIs are available via API discovery.

        Raises:
            RuntimeError: If required APIs are not found. This will prevent the backend
                        from initializing and cause the controller to fail fast.
        """
        # Validate NIMService API is available
        try:
            self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )
            logger.info(f"Validated NIMService API is available: {NIMSERVICE_API_VERSION} NIMService")
        except k8s_dynamic_exceptions.ResourceNotFoundError as e:
            logger.error(f"NIMService CRD not found: {e}")
            raise RuntimeError(
                f"NIMService API ({NIMSERVICE_API_VERSION}) not found. "
                f"The k8s-nim-operator must be installed before starting this backend."
            ) from e
        except Exception as e:
            logger.exception("Unexpected error validating NIMService API")
            raise RuntimeError(f"Failed to validate NIMService API ({NIMSERVICE_API_VERSION}): {e}") from e

        # Validate NIMCache API is available
        try:
            self._dynamic_client.resources.get(
                api_version=NIMCACHE_API_VERSION,
                kind="NIMCache",
            )
            logger.info(f"Validated NIMCache API is available: {NIMCACHE_API_VERSION} NIMCache")
        except k8s_dynamic_exceptions.ResourceNotFoundError as e:
            logger.error(f"NIMCache CRD not found: {e}")
            raise RuntimeError(
                f"NIMCache API ({NIMCACHE_API_VERSION}) not found. "
                f"The k8s-nim-operator must be installed before starting this backend."
            ) from e
        except Exception as e:
            logger.exception("Unexpected error validating NIMCache API")
            raise RuntimeError(f"Failed to validate NIMCache API ({NIMCACHE_API_VERSION}): {e}") from e

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

    def _get_host_url(self, resource_name: str) -> str:
        """Generate the Kubernetes service host URL for a deployment."""
        return f"http://{resource_name}.{self._k8s_namespace}.svc.cluster.local:8000"

    # ------------------------------------------------------------------
    # Pod log fetching and pod lookup (best-effort diagnostics)
    # ------------------------------------------------------------------

    def _fetch_pod_logs(self, pod_name: str) -> str:
        """Fetch recent pod logs for error reporting, truncated to LOG_MAX_CHARS."""
        try:
            core_v1 = k8s_client.CoreV1Api(self._k8s_client)
            logs = core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self._k8s_namespace,
                tail_lines=LOG_TAIL_LINES,
            )
            if len(logs) > LOG_MAX_CHARS:
                logs = logs[-LOG_MAX_CHARS:]
            return logs
        except Exception as e:
            logger.warning(
                "Failed to retrieve pod logs for error report", extra={"pod_name": pod_name, "error": str(e)}
            )
            return ""

    def _find_pod_name(self, resource_name: str) -> str | None:
        """Find the most recent pod name for a k8s Deployment (best-effort)."""
        try:
            apps_v1 = k8s_client.AppsV1Api(self._k8s_client)
            core_v1 = k8s_client.CoreV1Api(self._k8s_client)

            try:
                deployment = apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            except k8s_client.exceptions.ApiException:
                return None

            if not deployment.spec.selector or not deployment.spec.selector.match_labels:
                return None

            label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
            pods = core_v1.list_namespaced_pod(namespace=self._k8s_namespace, label_selector=label_selector)

            if not pods.items:
                return None

            pod = max(pods.items, key=lambda p: p.metadata.creation_timestamp)
            return pod.metadata.name
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Crash loop and pending timeout error builders
    # ------------------------------------------------------------------

    def _build_pending_timeout_error(
        self,
        resource_name: str,
        elapsed: float,
        pod_name: str | None,
    ) -> DeploymentStatusUpdate:
        """Build ERROR status update for a PENDING timeout."""
        error_stack = self._fetch_pod_logs(pod_name) if pod_name else ""
        kubectl_target = pod_name if pod_name else f"deployment/{resource_name}"
        status_msg = (
            f"Deployment timed out after {format_duration(elapsed)} waiting for NIM "
            f"to pass health checks (timeout: {format_duration(self._backend_config.pending_timeout_seconds)}).\n\n"
            f"Inspect the NIM pod logs with:\n"
            f"  kubectl logs -n {self._k8s_namespace} {kubectl_target}"
        )
        error_details: Dict[str, Any] = {
            "reason": "pending_timeout",
            "elapsed_seconds": int(elapsed),
            "timeout_seconds": self._backend_config.pending_timeout_seconds,
            "resource_name": resource_name,
            "namespace": self._k8s_namespace,
            "error_stack": error_stack if error_stack else None,
        }
        if pod_name:
            error_details["pod_name"] = pod_name
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=status_msg,
            error_details=error_details,
            host_url=None,
        )

    def _build_crash_loop_error(
        self,
        resource_name: str,
        pod_name: str,
        restart_count: int,
    ) -> DeploymentStatusUpdate:
        """Build ERROR status update for a crash loop."""
        error_stack = self._fetch_pod_logs(pod_name)
        status_msg = (
            f"Deployment entered crash loop after {restart_count} container restarts "
            f"(max: {self._backend_config.max_restart_count}).\n\n"
            f"Inspect the NIM pod logs with:\n"
            f"  kubectl logs -n {self._k8s_namespace} {pod_name}"
        )
        return DeploymentStatusUpdate(
            status="ERROR",
            status_message=status_msg,
            error_details={
                "reason": "crash_loop",
                "restart_count": restart_count,
                "max_restart_count": self._backend_config.max_restart_count,
                "pod_name": pod_name,
                "namespace": self._k8s_namespace,
                "resource_name": resource_name,
                "error_stack": error_stack if error_stack else None,
            },
            host_url=None,
        )

    # ------------------------------------------------------------------
    # Pod status helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_pod_restart_count(pod: k8s_client.V1Pod) -> int:
        """Get the maximum restart count across all containers in a pod."""
        if not pod.status.container_statuses:
            return 0
        return max((cs.restart_count or 0) for cs in pod.status.container_statuses)

    @staticmethod
    def _with_restart_info(status_msg: str, restart_count: int) -> str:
        """Append restart count to a status message when restarts > 0."""
        if restart_count > 0:
            return f"{status_msg}, restarts: {restart_count}"
        return status_msg

    def _check_crash_loop(self, pod: k8s_client.V1Pod, resource_name: str) -> DeploymentStatusUpdate | None:
        """Check if a pod is in a crash loop (restart count >= max_restart_count and waiting).

        Returns a DeploymentStatusUpdate with ERROR if crash loop detected, else None.
        """
        pod_name = pod.metadata.name
        logger.debug("Checking pod for crash loop", extra={"pod": pod_name, "phase": pod.status.phase})

        if not pod.status.container_statuses:
            logger.debug("Pod has no container statuses", extra={"pod": pod_name})
            return None

        max_restarts = self._backend_config.max_restart_count

        for idx, container_status in enumerate(pod.status.container_statuses):
            restart_count = container_status.restart_count or 0
            logger.debug(
                "Container status check",
                extra={"pod": pod_name, "container_index": idx, "restart_count": restart_count},
            )

            if restart_count >= max_restarts:
                if container_status.state and container_status.state.waiting:
                    waiting_reason = container_status.state.waiting.reason
                    logger.warning(
                        "Pod entered crash loop",
                        extra={
                            "pod": pod_name,
                            "restart_count": restart_count,
                            "max_restarts": max_restarts,
                            "waiting_reason": waiting_reason,
                        },
                    )
                    return self._build_crash_loop_error(resource_name, pod_name, restart_count)
                else:
                    logger.debug(
                        "Pod has restarts above threshold but is not in waiting state",
                        extra={"pod": pod_name, "container_index": idx, "restart_count": restart_count},
                    )

        logger.debug("Crash loop check complete, no crash loop detected", extra={"pod": pod_name})
        return None

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

    def _get_pod_status_from_deployment(self, resource_name: str) -> DeploymentStatusUpdate:
        """Get status message from pod events for a deployment.

        Returns:
            DeploymentStatusUpdate with status (PENDING or ERROR) and descriptive message.
            Crash loop detection is performed here; PENDING timeout is handled by the caller.
        """
        logger.info(f"Getting pod status for deployment: {resource_name}")
        try:
            apps_v1 = k8s_client.AppsV1Api(self._k8s_client)
            core_v1 = k8s_client.CoreV1Api(self._k8s_client)

            try:
                deployment = apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            except k8s_client.exceptions.ApiException as e:
                if e.status == 404:
                    return DeploymentStatusUpdate(
                        status="PENDING", status_message="Waiting for k8s deployment to be created", host_url=None
                    )
                raise

            if not deployment.spec.selector or not deployment.spec.selector.match_labels:
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Waiting for k8s deployment - invalid selector configuration",
                    host_url=None,
                )

            label_selector = ",".join([f"{k}={v}" for k, v in deployment.spec.selector.match_labels.items()])
            pods = core_v1.list_namespaced_pod(namespace=self._k8s_namespace, label_selector=label_selector)

            if not pods.items:
                logger.info(f"No pods found for deployment {resource_name}")
                return DeploymentStatusUpdate(
                    status="PENDING", status_message="Waiting for k8s deployment - no pods created yet", host_url=None
                )

            logger.info(f"Found {len(pods.items)} pod(s) for deployment {resource_name}")

            pod: k8s_client.V1Pod = max(pods.items, key=lambda p: p.metadata.creation_timestamp)
            logger.info(f"Checking most recent pod: {pod.metadata.name}")

            crash_result = self._check_crash_loop(pod, resource_name)
            if crash_result:
                return crash_result

            restart_count = self._get_pod_restart_count(pod)

            events = core_v1.list_namespaced_event(
                namespace=self._k8s_namespace, field_selector=f"involvedObject.name={pod.metadata.name}"
            )

            if not events.items:
                if pod.status.phase == "Pending" and pod.status.container_statuses:
                    for container_status in pod.status.container_statuses:
                        if container_status.state and container_status.state.waiting:
                            reason = container_status.state.waiting.reason
                            message = container_status.state.waiting.message or ""
                            status_msg = f"{reason}: {message}" if message else reason
                            status_msg = self._with_restart_info(status_msg, restart_count)
                            return DeploymentStatusUpdate(status="PENDING", status_message=status_msg, host_url=None)
                pod_status = pod.status.phase.lower() if pod.status.phase else "unknown"
                status_msg = f"Waiting for k8s deployment - pod status is {pod_status}"
                status_msg = self._with_restart_info(status_msg, restart_count)
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message=status_msg,
                    host_url=None,
                )

            recent_event = max(
                events.items, key=lambda e: e.last_timestamp or e.event_time or e.metadata.creation_timestamp
            )

            reason = recent_event.reason
            message = recent_event.message

            for search_string, return_message in POD_EVENT_TO_MESSAGE_MAP.items():
                if search_string in message.lower():
                    status_msg = self._with_restart_info(return_message, restart_count)
                    return DeploymentStatusUpdate(status="PENDING", status_message=status_msg, host_url=None)

            if len(message) > 200:
                message = message[:197] + "..."

            status_msg = self._with_restart_info(f"{reason}: {message}", restart_count)
            return DeploymentStatusUpdate(status="PENDING", status_message=status_msg, host_url=None)

        except Exception as e:
            logger.warning(f"Failed to get pod status for deployment {resource_name}: {e}")
            return DeploymentStatusUpdate(status="PENDING", status_message="Waiting for k8s deployment", host_url=None)

    def _resolve_model_source(
        self,
        model_entity: Optional[ModelEntity],
        nim_config: Any,
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

    async def create_model_deployment(
        self, deployment: ModelDeployment, config: ModelDeploymentConfig, model_entity: Optional[ModelEntity] = None
    ) -> DeploymentStatusUpdate:
        """Create a new model deployment via NIM Operator."""
        logger.info(
            f"Creating NIMService: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )

        # Check if Files service model (SFT or fileset) and create NIMCache if needed
        nimcache_name = None
        weights_type = get_model_weights_type(
            model_deployment=deployment,
            model_deployment_config=config,
            model_entity=model_entity,
        )
        if weights_type == ModelWeightsType.FILES_SERVICE:
            logger.info(
                f"Files service model detected for deployment {deployment.workspace}/{deployment.name}, creating NIMCache"
            )

            nim_config = deployment_config_view(config)
            pvc_size = nim_config.disk_size if nim_config.disk_size else self._backend_config.default_pvc_size

            try:
                model_namespace, model_name, model_revision = self._resolve_model_source(model_entity, nim_config)

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

                nimcache_resource_name = self._get_nimcache_resource_name(deployment)

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
            resource_name = self._get_resource_name(deployment)

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

    async def update_model_deployment(
        self, deployment: ModelDeployment, config: ModelDeploymentConfig, model_entity: Optional[ModelEntity] = None
    ) -> DeploymentStatusUpdate:
        """Update an existing model deployment via NIM Operator."""
        logger.info(
            f"Updating NIMService: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )

        # Check if Files service model (SFT or fileset) and create/update NIMCache if needed
        nimcache_name = None
        weights_type = get_model_weights_type(
            model_deployment=deployment,
            model_deployment_config=config,
            model_entity=model_entity,
        )
        if weights_type == ModelWeightsType.FILES_SERVICE:
            logger.info(
                f"Files service model detected for deployment update {deployment.workspace}/{deployment.name}, creating/updating NIMCache"
            )

            nim_config = deployment_config_view(config)
            pvc_size = nim_config.disk_size if nim_config.disk_size else self._backend_config.default_pvc_size

            try:
                model_namespace, model_name, model_revision = self._resolve_model_source(model_entity, nim_config)

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

                nimcache_resource_name = self._get_nimcache_resource_name(deployment)

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
            resource_name = self._get_resource_name(deployment)

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
            return await self.create_model_deployment(deployment, config)

        except Exception as e:
            logger.error(f"Failed to update NIMService for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to update deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def get_model_deployment_status(self, deployment: ModelDeployment) -> DeploymentStatusUpdate:
        """Get the current status of a NIM Operator model deployment.

        In addition to the NIMService/pod status, this method enforces:
        - PENDING timeout: if the deployment has been alive longer than
          ``pending_timeout_seconds`` (from config) and is still PENDING,
          transition to ERROR with diagnostic information.
        - Crash loop detection is handled inside ``_get_pod_status_from_deployment``.
        """
        logger.debug(
            f"Checking NIMService status: {deployment.workspace}/{deployment.name} "
            f"(version: {deployment.entity_version})"
        )

        try:
            resource_name = self._get_resource_name(deployment)

            result = self._get_nimservice_status(resource_name)

            if result.status == "PENDING":
                elapsed = deployment_elapsed_seconds(deployment)

                if elapsed >= self._backend_config.pending_timeout_seconds:
                    pod_name = self._find_pod_name(resource_name)
                    return self._build_pending_timeout_error(resource_name, elapsed, pod_name)

                # Use a stable message (no elapsed/timeout) so we don't create a new history entry every poll

            return result
        except Exception as e:
            logger.error(f"Failed to get status for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Unable to determine deployment status due to a service backend error",
                host_url=None,
            )

    def _delete_resources_by_model_deployment_id(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete NIMService and NIMCache for the given model deployment (by workspace/name)."""
        nimservice_name = get_deployment_resource_name(workspace, name)
        nimcache_name = get_nimcache_resource_name(workspace, name)
        try:
            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )

            try:
                nimservice_api.delete(
                    name=nimservice_name,
                    namespace=self._k8s_namespace,
                )
                logger.info(f"Successfully deleted NIMService {self._k8s_namespace}/{nimservice_name}")
            except k8s_dynamic_exceptions.NotFoundError:
                logger.info(f"NIMService {nimservice_name} not found, may have been already deleted")

            # Try to delete associated NIMCache if it exists
            try:
                nimcache_api = self._dynamic_client.resources.get(
                    api_version=NIMCACHE_API_VERSION,
                    kind="NIMCache",
                )
                nimcache_api.delete(
                    name=nimcache_name,
                    namespace=self._k8s_namespace,
                )
                logger.info(f"Successfully deleted NIMCache {self._k8s_namespace}/{nimcache_name}")
            except k8s_dynamic_exceptions.NotFoundError:
                logger.debug(f"No NIMCache found for {nimcache_name}, skipping cleanup")
            except Exception as e:
                logger.warning(f"Error deleting NIMCache {nimcache_name}: {e}")

            return DeploymentStatusUpdate(
                status="DELETED",
                status_message="NIMService deletion initiated successfully",
                host_url=None,
            )

        except Exception as e:
            logger.exception(f"Failed to delete NIMService {nimservice_name}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to delete deployment {nimservice_name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    async def delete_model_deployment(self, workspace: str, name: str) -> DeploymentStatusUpdate:
        """Delete a NIM Operator model deployment by workspace and name (model deployment ID)."""
        logger.info(f"Deleting NIMService: {workspace}/{name}")
        return self._delete_resources_by_model_deployment_id(workspace, name)

    async def list_managed_deployment_names(self) -> list[str]:
        """List deployment names (workspace/name) the backend currently manages via NIMService labels."""
        try:
            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )
            result = nimservice_api.get(
                namespace=self._k8s_namespace,
                label_selector=f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}",
            )
        except Exception as e:
            logger.warning(f"Failed to list NIMServices for orphan reconciliation: {e}")
            return []

        items = getattr(result, "items", None) or []
        seen: set[str] = set()
        for item in items:
            labels = getattr(getattr(item, "metadata", None), "labels", None) or {}
            if isinstance(labels, dict):
                workspace = labels.get("nmp.nvidia.com/deployment-workspace")
                name = labels.get("nmp.nvidia.com/deployment-name")
                if workspace and name:
                    seen.add(f"{workspace}/{name}")
        return sorted(seen)
