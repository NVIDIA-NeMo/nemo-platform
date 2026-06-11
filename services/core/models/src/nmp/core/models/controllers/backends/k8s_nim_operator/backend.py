# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Kubernetes NIM Operator backend implementation for Models Controller service."""

import os
from logging import getLogger
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.common.config import get_platform_config
from nmp.core.models.app import (
    ModelWeightsType,
    get_deployment_resource_name,
    get_model_weights_type,
    get_nimcache_resource_name,
    parse_model_name_revision,
)
from nmp.core.models.app.constants import MODEL_MANAGED_BY_LABEL, MODEL_MANAGED_BY_MODELS_CONTROLLER
from nmp.core.models.controllers.backends import vllm_compiler
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate, ServiceBackend
from nmp.core.models.controllers.backends.common import (
    LOG_MAX_CHARS,
    LOG_TAIL_LINES,
    deployment_config_view,
    deployment_elapsed_seconds,
    format_duration,
)
from nmp.core.models.controllers.backends.engine import (
    ENGINE_GENERIC,
    ENGINE_VLLM,
    config_engine,
    resolve_health_path,
)
from nmp.core.models.controllers.backends.k8s_nim_operator import vllm_k8s_compiler as vk8s
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
        self._core_v1: k8s_client.CoreV1Api | None = None
        self._apps_v1: k8s_client.AppsV1Api | None = None
        self._batch_v1: k8s_client.BatchV1Api | None = None
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
        self._core_v1 = k8s_client.CoreV1Api(self._k8s_client)
        self._apps_v1 = k8s_client.AppsV1Api(self._k8s_client)
        self._batch_v1 = k8s_client.BatchV1Api(self._k8s_client)

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
        """Create a new model deployment.

        Dispatches on ``config.engine``: the vLLM path emits native Kubernetes
        objects directly (no operator); the NIM path emits NIMService/NIMCache CRs
        for the operator to reconcile (unchanged).
        """
        engine = config_engine(config)
        if engine == ENGINE_VLLM:
            return await self._create_vllm_deployment(deployment, config, model_entity)
        if engine == ENGINE_GENERIC:
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="The 'generic' engine is not yet supported on the k8s backend.",
                error_details={"error": "unsupported_engine", "engine": engine},
                host_url=None,
            )

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

    # ==================================================================
    # vLLM path (native Kubernetes objects, no operator)
    # ==================================================================

    def _vllm_model_source(self, model_entity: Optional[ModelEntity], view: Any) -> tuple[str, str]:
        """Resolve the puller's model repo (``namespace/name``) and a source tag.

        The source tag (``namespace/name@revision``) is stamped on the PVC + Job so
        the update path can detect a weight-source change and decide to re-pull.
        """
        namespace, name, revision = self._resolve_model_source(model_entity, view)
        if not namespace or not name:
            raise ValueError(f"Cannot resolve model source for vLLM deployment: namespace={namespace}, name={name}")
        model_repo = f"{namespace}/{name}"
        source_tag = f"{model_repo}@{revision}" if revision else model_repo
        return model_repo, source_tag

    def _vllm_objects_exist(self, resource_name: str) -> bool:
        """True if directly-emitted vLLM objects for this deployment exist.

        Used only as a fallback when no config is available to read the engine
        from. Checks the serving Deployment first (the puller Job is deleted once
        the Deployment is created, so the Job alone is not a reliable marker), then
        the puller Job for the pre-Deployment phase. Any lookup failure (including
        404) means "not (yet) a vLLM deployment" -> the NIMService status path.
        """

        def _has_vllm_engine_label(obj) -> bool:
            labels = getattr(getattr(obj, "metadata", None), "labels", None)
            return isinstance(labels, dict) and labels.get("nmp.nvidia.com/engine") == ENGINE_VLLM

        try:
            dep = self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            if _has_vllm_engine_label(dep):
                return True
        except Exception:
            pass
        try:
            job = self._batch_v1.read_namespaced_job(
                name=vk8s.pull_job_name(resource_name), namespace=self._k8s_namespace
            )
        except Exception:
            return False
        return _has_vllm_engine_label(job)

    def _pvc_exists(self, resource_name: str) -> bool:
        """True if the model-weights PVC for this deployment exists."""
        try:
            self._core_v1.read_namespaced_persistent_volume_claim(
                name=vk8s.pvc_name(resource_name), namespace=self._k8s_namespace
            )
            return True
        except k8s_client.exceptions.ApiException as e:
            if e.status == 404:
                return False
            raise

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

    async def _create_vllm_deployment(
        self, deployment: ModelDeployment, config: ModelDeploymentConfig, model_entity: Optional[ModelEntity]
    ) -> DeploymentStatusUpdate:
        """Create phase P0: emit the PVC + weight-puller Job.

        The Deployment + Service are created later by the status path once the Job
        completes (controller-side weight-readiness gating).
        """
        logger.info(
            f"Creating vLLM deployment: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )
        try:
            resource_name = self._get_resource_name(deployment)
            view = deployment_config_view(config)
            model_repo, source_tag = self._vllm_model_source(model_entity, view)
            disk_size = view.disk_size or self._backend_config.default_pvc_size

            pvc = vk8s.compile_pvc(
                resource_name=resource_name,
                workspace=deployment.workspace,
                name=deployment.name,
                engine=ENGINE_VLLM,
                disk_size=disk_size,
                storage_class=self._backend_config.default_storage_class,
                model_source=source_tag,
                namespace=self._k8s_namespace,
                annotations=self._backend_config.default_annotations,
            )
            job = vk8s.compile_puller_job(
                resource_name=resource_name,
                workspace=deployment.workspace,
                name=deployment.name,
                engine=ENGINE_VLLM,
                image=self._huggingface_model_puller,
                args=["download", model_repo, "--local-dir", vk8s.MODEL_STORE_PATH],
                env={"HF_ENDPOINT": self._remote_files_hf_url(), "HF_TOKEN": "service:models"},
                gpu=view.gpu,
                namespace=self._k8s_namespace,
                service_account_name=self._backend_config.service_account_name,
                image_pull_secret=self._backend_config.huggingface_model_puller_image_pull_secret,
                user_id=self._backend_config.default_user_id,
                group_id=self._backend_config.default_group_id,
                model_source=source_tag,
            )

            self._create_or_skip(self._core_v1.create_namespaced_persistent_volume_claim, pvc, "PVC")
            self._create_or_skip(self._batch_v1.create_namespaced_job, job, "puller Job")

            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Provisioning model weights",
                host_url=self._get_host_url(resource_name),
            )
        except Exception as e:
            logger.error(f"Failed to create vLLM deployment for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to create deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    def _create_or_skip(self, create_fn, body, kind: str) -> None:
        """Create a namespaced object, tolerating 409 Conflict (already exists)."""
        try:
            create_fn(namespace=self._k8s_namespace, body=body)
            logger.info(f"Created {kind} {body.metadata.name} in {self._k8s_namespace}")
        except k8s_client.exceptions.ApiException as e:
            if e.status == 409:
                logger.info(f"{kind} {body.metadata.name} already exists, skipping creation")
                return
            raise

    async def _get_vllm_status(
        self,
        deployment: ModelDeployment,
        resource_name: str,
        config: Optional[ModelDeploymentConfig],
        model_entity: Optional[ModelEntity],
    ) -> DeploymentStatusUpdate:
        """Drive the vLLM phased lifecycle and project status.

        Reads the puller Job + (once created) the Deployment. When the Job has
        completed and the Deployment doesn't exist yet, this advances creation
        (phase P3) by emitting the Deployment + Service.
        """
        # The serving Deployment is the source of truth once it exists. We create
        # it at P3 and delete the puller Job in the same step (to release the RWO
        # volume), so a present Deployment means "past the pull phase" -- project
        # its readiness and do NOT consult the (now-absent) Job.
        try:
            self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
            deployment_exists = True
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            deployment_exists = False

        if deployment_exists:
            return self._project_deployment_readiness(resource_name)

        # No Deployment yet: we're still in the pull phase. Consult the puller Job.
        job_name = vk8s.pull_job_name(resource_name)
        try:
            job = self._batch_v1.read_namespaced_job(name=job_name, namespace=self._k8s_namespace)
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise
            # Job absent. This is either (a) the transient P3 window after we
            # deleted a *succeeded* puller Job to release the RWO volume (the PVC
            # still exists and holds the weights -> resume P3 by creating the
            # serving objects), or (b) genuine drift (PVC also gone -> LOST).
            if self._pvc_exists(resource_name) and config is not None:
                return self._create_vllm_serving_objects(deployment, resource_name, config, model_entity)
            return DeploymentStatusUpdate(
                status="LOST",
                status_message="Weight-puller Job and PVC not found; resources may have been deleted externally.",
                host_url=None,
            )

        job_status = job.status
        if job_status and job_status.failed and job_status.failed >= 1 and not (job_status.succeeded or 0):
            pod_name = self._find_job_pod_name(job_name)
            logs = self._fetch_pod_logs(pod_name) if pod_name else ""
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="Model weight download failed.",
                error_details={"reason": "weight_pull_failed", "job": job_name, "error_stack": logs or None},
                host_url=None,
            )

        job_complete = bool(job_status and job_status.succeeded and job_status.succeeded >= 1)
        if not job_complete:
            return DeploymentStatusUpdate(status="PENDING", status_message="Downloading model weights", host_url=None)

        # Job complete and no Deployment yet: phase P3. Need the config to compile
        # the serving spec (the controller threads it through).
        if config is None:
            logger.warning(
                "vLLM puller Job for %s complete but no config provided; cannot create serving Deployment",
                resource_name,
            )
            return DeploymentStatusUpdate(
                status="PENDING", status_message="Waiting to start vLLM server", host_url=None
            )
        return self._create_vllm_serving_objects(deployment, resource_name, config, model_entity)

    def _project_deployment_readiness(self, resource_name: str) -> DeploymentStatusUpdate:
        """Map the serving Deployment's status to a DeploymentStatusUpdate."""
        deployment = self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)
        ready = (deployment.status.ready_replicas or 0) if deployment.status else 0
        if ready >= 1:
            return DeploymentStatusUpdate(status="READY", status_message="", host_url=self._get_host_url(resource_name))
        # Not ready yet: reuse the pod-drilldown (crash loop, image pull, events).
        return self._get_pod_status_from_deployment(resource_name)

    def _create_vllm_serving_objects(
        self,
        deployment: ModelDeployment,
        resource_name: str,
        config: ModelDeploymentConfig,
        model_entity: Optional[ModelEntity],
    ) -> DeploymentStatusUpdate:
        """Create the vLLM Deployment + Service after the puller Job has completed.

        Before creating the Deployment, the completed puller Job is deleted so its
        pod releases the ReadWriteOnce PVC's volume attachment: a completed pod
        keeps the volume attached to its node, which would otherwise block the
        server pod from mounting the same RWO PVC if it schedules onto a different
        node (Multi-Attach error). This runs only on the success path (the Job has
        succeeded); a failed Job is left in place so the status path can read it +
        its logs and report ERROR.

        Sets ownerReferences (PVC, Service -> Deployment) so deleting the
        Deployment cascades the rest. The serving spec is compiled from ``config``
        (the controller threads it through ``get_model_deployment_status``).
        """
        # Release the RWO volume from the completed puller before the server needs
        # it. Idempotent: if already deleted on a prior poll, _delete_puller_job
        # treats NotFound as done.
        if not self._delete_puller_job(resource_name):
            return DeploymentStatusUpdate(
                status="PENDING",
                status_message="Releasing model weights volume",
                host_url=self._get_host_url(resource_name),
            )

        view = deployment_config_view(config)

        engine = ENGINE_VLLM
        health_path = resolve_health_path(engine, view)
        image_name, image_tag = vllm_compiler.resolve_vllm_image(
            view, self._backend_config.default_vllm_image, self._backend_config.default_vllm_image_tag
        )
        args = vllm_compiler.compile_vllm_args(view, model_entity)
        env = vllm_compiler.compile_vllm_env_vars(view)

        startup_grace = self._backend_config.default_startup_probe_grace_period_seconds or 600

        init_containers, sidecar_containers = self._build_lora_containers(deployment, view, model_entity)

        dep_obj = vk8s.compile_deployment(
            resource_name=resource_name,
            workspace=deployment.workspace,
            name=deployment.name,
            engine=engine,
            image=f"{image_name}:{image_tag}",
            args=args,
            health_path=health_path,
            env=env,
            gpu=view.gpu,
            namespace=self._k8s_namespace,
            service_account_name=self._backend_config.service_account_name,
            user_id=self._backend_config.default_user_id,
            group_id=self._backend_config.default_group_id,
            shared_memory_size_limit=self._backend_config.default_shared_memory_size_limit,
            startup_grace_seconds=startup_grace,
            init_containers=init_containers,
            sidecar_containers=sidecar_containers,
        )
        svc_obj = vk8s.compile_service(
            resource_name=resource_name,
            workspace=deployment.workspace,
            name=deployment.name,
            engine=engine,
            namespace=self._k8s_namespace,
        )

        try:
            created_dep = self._apps_v1.create_namespaced_deployment(namespace=self._k8s_namespace, body=dep_obj)
            logger.info(f"Created vLLM Deployment {resource_name} in {self._k8s_namespace}")
        except k8s_client.exceptions.ApiException as e:
            if e.status != 409:
                raise
            created_dep = self._apps_v1.read_namespaced_deployment(name=resource_name, namespace=self._k8s_namespace)

        # Owner reference -> Deployment, so PVC/Service cascade on delete. (The
        # puller Job was already deleted above to release the RWO volume.)
        owner_ref = k8s_client.V1OwnerReference(
            api_version="apps/v1",
            kind="Deployment",
            name=created_dep.metadata.name,
            uid=created_dep.metadata.uid,
            controller=True,
            block_owner_deletion=True,
        )
        svc_obj.metadata.owner_references = [owner_ref]
        self._create_or_skip(self._core_v1.create_namespaced_service, svc_obj, "Service")
        self._set_owner_reference_on_pvc(resource_name, owner_ref)

        return DeploymentStatusUpdate(status="PENDING", status_message="Starting vLLM server", host_url=None)

    def _delete_puller_job(self, resource_name: str) -> bool:
        """Delete the puller Job and confirm its pod is gone (releases RWO volume).

        Deletes the Job with foreground/background propagation so its pod is
        removed, freeing the volume attachment for the server pod. Returns True
        once no puller pod remains; False if a pod is still terminating (caller
        should retry on the next poll). Idempotent: a missing Job/pod counts as
        released.
        """
        job_name = vk8s.pull_job_name(resource_name)
        try:
            self._batch_v1.delete_namespaced_job(
                name=job_name,
                namespace=self._k8s_namespace,
                propagation_policy="Background",
            )
            logger.info(f"Deleted puller Job {job_name} to release the model-weights volume")
        except k8s_client.exceptions.ApiException as e:
            if e.status != 404:
                raise

        # The volume stays attached until the pod object is gone, so confirm.
        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._k8s_namespace, label_selector=f"job-name={job_name}"
            )
        except Exception:
            return True
        return len(pods.items) == 0

    def _build_lora_containers(
        self, deployment: ModelDeployment, view: Any, model_entity: Optional[ModelEntity]
    ) -> tuple[Optional[list], Optional[list]]:
        """Build the LoRA init container + adapter sidecar for a vLLM Deployment.

        Returns ``(init_containers, sidecar_containers)``; both ``None`` when LoRA
        is not enabled.

        - The init container pre-creates ``/scratch/loras`` (vLLM's filesystem
          resolver validates the dir exists at startup).
        - The sidecar runs the engine-agnostic ``nmp-api`` adapters controller,
          pointed at the same dir, rewriting each adapter's base-model name to the
          served model path (``VLLM_LORA_BASE_MODEL_OVERRIDE=/model-store``).
        """
        if not view.lora_enabled:
            return None, None

        lora_dir = vllm_compiler.VLLM_LORA_CACHE_DIR
        platform_config = get_platform_config()
        image_pull_secrets = [secret.name for secret in platform_config.image_pull_secrets]
        sidecar_image = f"{platform_config.image_registry}/nmp-api:{platform_config.image_tag}"

        init_container = k8s_client.V1Container(
            name="lora-cache-init",
            image=f"{self._backend_config.busybox_image}:{self._backend_config.busybox_image_tag}",
            command=["sh", "-c", f"mkdir -p {lora_dir} && chmod -R 777 {lora_dir}"],
            volume_mounts=[k8s_client.V1VolumeMount(name="scratch", mount_path=vk8s.SCRATCH_PATH)],
        )

        sidecar_env = {
            "NIM_PEFT_SOURCE": lora_dir,
            "NIM_PEFT_REFRESH_INTERVAL": str(self._backend_config.peft_refresh_interval),
            "VLLM_LORA_BASE_MODEL_OVERRIDE": vllm_compiler.MODEL_STORE_PATH,
            "NMP_MODEL_ENTITY_WORKSPACE": deployment.workspace,
            "NMP_MODEL_ENTITY_NAME": deployment.name,
        }
        if model_entity is not None:
            sidecar_env["NMP_MODEL_ENTITY_WORKSPACE"] = model_entity.workspace
            sidecar_env["NMP_MODEL_ENTITY_NAME"] = model_entity.name
        sidecar_env.update(platform_config.to_shared_envvars())

        sidecar = k8s_client.V1Container(
            name="lora-sidecar",
            image=sidecar_image,
            image_pull_policy="IfNotPresent",
            command=["nemo", "services", "run", "--sidecars", "adapters"],
            env=[k8s_client.V1EnvVar(name=k, value=str(v)) for k, v in sidecar_env.items()],
            volume_mounts=[
                k8s_client.V1VolumeMount(name="model-store", mount_path=vk8s.MODEL_STORE_PATH, read_only=True),
                k8s_client.V1VolumeMount(name="scratch", mount_path=vk8s.SCRATCH_PATH),
            ],
        )
        # imagePullSecrets are pod-level; the compiler sets them from the puller
        # secret, but the sidecar image comes from the platform registry. Attach
        # via the sidecar's own spec is not possible (pod-level only), so rely on
        # the pod's service account / pull secret. (Platform pull secrets are
        # applied at the chart level for the models SA.)
        _ = image_pull_secrets  # documented: pod-level pull secrets handled by SA
        return [init_container], [sidecar]

    def _set_owner_reference_on_pvc(self, resource_name: str, owner_ref: k8s_client.V1OwnerReference) -> None:
        """Patch the PVC to be owned by the Deployment (best-effort).

        The puller Job is deleted before the Deployment is created (to release the
        RWO volume), so only the PVC needs an ownerRef here; the Service gets its
        ownerRef at create time.
        """
        patch = {"metadata": {"ownerReferences": [self._k8s_client.sanitize_for_serialization(owner_ref)]}}
        try:
            self._core_v1.patch_namespaced_persistent_volume_claim(
                name=vk8s.pvc_name(resource_name), namespace=self._k8s_namespace, body=patch
            )
        except Exception as e:
            logger.warning(f"Failed to set ownerReference on PVC for {resource_name}: {e}")

    def _find_job_pod_name(self, job_name: str) -> str | None:
        """Find the most recent pod for a Job (best-effort, for failure logs)."""
        try:
            pods = self._core_v1.list_namespaced_pod(
                namespace=self._k8s_namespace, label_selector=f"job-name={job_name}"
            )
            if not pods.items:
                return None
            return max(pods.items, key=lambda p: p.metadata.creation_timestamp).metadata.name
        except Exception:
            return None

    async def _update_vllm_deployment(
        self, deployment: ModelDeployment, config: ModelDeploymentConfig, model_entity: Optional[ModelEntity]
    ) -> DeploymentStatusUpdate:
        """Update a vLLM deployment, applying the re-pull policy.

        Weights are only re-pulled when the model source (name/revision) changes.
        Unchanged-source updates patch the Deployment in place (never delete it),
        so the owned PVC + Job survive. A changed source deletes the Deployment
        (cascading PVC + Job) and drops back to the phased create.
        """
        logger.info(
            f"Updating vLLM deployment: {deployment.workspace}/{deployment.name} (version: {deployment.entity_version})"
        )
        try:
            resource_name = self._get_resource_name(deployment)
            view = deployment_config_view(config)
            _, source_tag = self._vllm_model_source(model_entity, view)

            existing_source = self._existing_model_source(resource_name)
            if existing_source is not None and existing_source != source_tag:
                logger.info(
                    f"Model source changed ({existing_source} -> {source_tag}); re-pulling weights for {resource_name}"
                )
                self._delete_vllm_resources(resource_name)
                return await self._create_vllm_deployment(deployment, config, model_entity)

            # Unchanged source: patch the Deployment + Service in place if present,
            # else (still in the pull phase) recreate the puller objects if missing.
            if self._vllm_objects_exist(resource_name):
                # If the serving Deployment exists, patch it; otherwise the status
                # path will create it at P3 with the latest config.
                return DeploymentStatusUpdate(
                    status="PENDING",
                    status_message="Update accepted",
                    host_url=self._get_host_url(resource_name),
                )
            return await self._create_vllm_deployment(deployment, config, model_entity)
        except Exception as e:
            logger.error(f"Failed to update vLLM deployment for {deployment.workspace}/{deployment.name}: {e}")
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message=f"Failed to update deployment {deployment.workspace}/{deployment.name} due to a service backend error",
                error_details={"error": str(e), "error_type": type(e).__name__},
                host_url=None,
            )

    def _existing_model_source(self, resource_name: str) -> str | None:
        """Read the model-source annotation off the existing puller Job, if any."""
        try:
            job = self._batch_v1.read_namespaced_job(
                name=vk8s.pull_job_name(resource_name), namespace=self._k8s_namespace
            )
        except k8s_client.exceptions.ApiException:
            return None
        annotations = (job.metadata.annotations or {}) if job.metadata else {}
        return annotations.get(vk8s.MODEL_SOURCE_ANNOTATION)

    def _delete_vllm_resources(self, resource_name: str) -> None:
        """Delete the directly-emitted vLLM objects by name (idempotent)."""
        deleters = [
            (self._apps_v1.delete_namespaced_deployment, resource_name, "Deployment"),
            (self._core_v1.delete_namespaced_service, resource_name, "Service"),
            (self._batch_v1.delete_namespaced_job, vk8s.pull_job_name(resource_name), "puller Job"),
            (
                self._core_v1.delete_namespaced_persistent_volume_claim,
                vk8s.pvc_name(resource_name),
                "PVC",
            ),
        ]
        for delete_fn, obj_name, kind in deleters:
            try:
                delete_fn(name=obj_name, namespace=self._k8s_namespace)
                logger.info(f"Deleted {kind} {obj_name} in {self._k8s_namespace}")
            except k8s_client.exceptions.ApiException as e:
                if e.status == 404:
                    continue
                logger.warning(f"Error deleting {kind} {obj_name}: {e}")

    async def update_model_deployment(
        self, deployment: ModelDeployment, config: ModelDeploymentConfig, model_entity: Optional[ModelEntity] = None
    ) -> DeploymentStatusUpdate:
        """Update an existing model deployment."""
        engine = config_engine(config)
        if engine == ENGINE_VLLM:
            return await self._update_vllm_deployment(deployment, config, model_entity)
        if engine == ENGINE_GENERIC:
            return DeploymentStatusUpdate(
                status="ERROR",
                status_message="The 'generic' engine is not yet supported on the k8s backend.",
                error_details={"error": "unsupported_engine", "engine": engine},
                host_url=None,
            )

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

    async def get_model_deployment_status(
        self,
        deployment: ModelDeployment,
        config: Optional[ModelDeploymentConfig] = None,
        model_entity: Optional[ModelEntity] = None,
    ) -> DeploymentStatusUpdate:
        """Get the current status of a model deployment.

        In addition to the NIMService/pod status, this method enforces:
        - PENDING timeout: if the deployment has been alive longer than
          ``pending_timeout_seconds`` (from config) and is still PENDING,
          transition to ERROR with diagnostic information.
        - Crash loop detection is handled inside ``_get_pod_status_from_deployment``.

        For the vLLM path, ``config`` is required to advance creation (emit the
        serving Deployment + Service once the weight-puller Job completes).
        """
        logger.debug(
            f"Checking deployment status: {deployment.workspace}/{deployment.name} "
            f"(version: {deployment.entity_version})"
        )

        try:
            resource_name = self._get_resource_name(deployment)

            # Prefer the engine from the config when the controller provides it;
            # fall back to detecting the vLLM path by the presence of its raw
            # puller Job (e.g. orphan reconciliation paths that lack a config).
            if config is not None:
                is_vllm = config_engine(config) == ENGINE_VLLM
            else:
                is_vllm = self._vllm_objects_exist(resource_name)

            if is_vllm:
                result = await self._get_vllm_status(deployment, resource_name, config, model_entity)
            else:
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

            # Also tear down any directly-emitted vLLM objects (idempotent; delete
            # has no config/engine, so we clean up both paths by name). Deleting the
            # Deployment cascades its owned PVC/Job/Service, but the puller objects
            # may exist before the Deployment (phases P0-P2), so delete explicitly.
            self._delete_vllm_resources(nimservice_name)

            return DeploymentStatusUpdate(
                status="DELETED",
                status_message="Deployment deletion initiated successfully",
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
        """List deployment names (workspace/name) the backend manages.

        Unions the operator path (NIMServices) and the directly-emitted vLLM path
        (raw Deployments), both labelled by the same managed-by + workspace/name
        labels, for orphan reconciliation.
        """
        label_selector = f"{MODEL_MANAGED_BY_LABEL}={MODEL_MANAGED_BY_MODELS_CONTROLLER}"
        seen: set[str] = set()

        # Operator path: NIMServices.
        try:
            nimservice_api = self._dynamic_client.resources.get(
                api_version=NIMSERVICE_API_VERSION,
                kind="NIMService",
            )
            result = nimservice_api.get(namespace=self._k8s_namespace, label_selector=label_selector)
            for item in getattr(result, "items", None) or []:
                labels = getattr(getattr(item, "metadata", None), "labels", None) or {}
                if isinstance(labels, dict):
                    workspace = labels.get("nmp.nvidia.com/deployment-workspace")
                    name = labels.get("nmp.nvidia.com/deployment-name")
                    if workspace and name:
                        seen.add(f"{workspace}/{name}")
        except k8s_dynamic_exceptions.ForbiddenError:
            # No RBAC for the NIM CRDs (e.g. a vLLM-only deployment). Not an error.
            logger.debug("No access to NIMServices for orphan reconciliation; skipping NIM path")
        except Exception as e:
            logger.warning(f"Failed to list NIMServices for orphan reconciliation: {e}")

        # vLLM path: directly-emitted Deployments.
        try:
            deployments = self._apps_v1.list_namespaced_deployment(
                namespace=self._k8s_namespace, label_selector=label_selector
            )
            for dep in deployments.items:
                labels = (dep.metadata.labels or {}) if dep.metadata else {}
                workspace = labels.get(vk8s.DEPLOYMENT_WORKSPACE_LABEL)
                name = labels.get(vk8s.DEPLOYMENT_NAME_LABEL)
                if workspace and name:
                    seen.add(f"{workspace}/{name}")
        except Exception as e:
            logger.warning(f"Failed to list vLLM Deployments for orphan reconciliation: {e}")

        return sorted(seen)
