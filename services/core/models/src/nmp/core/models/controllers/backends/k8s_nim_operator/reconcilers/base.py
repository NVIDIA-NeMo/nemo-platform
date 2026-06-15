# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reconciler interface + shared Kubernetes status helpers.

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

The shared, engine-agnostic Kubernetes status helpers (pod log fetch, crash-loop
detection, pod-status drill-down, pending-timeout/crash-loop error builders) live
on :class:`BaseReconciler` because both reconcilers project status from the same
underlying pod/Deployment/event objects.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import getLogger
from typing import Any, Dict, Optional

from kubernetes import client as k8s_client
from kubernetes.dynamic import exceptions as k8s_dynamic_exceptions
from nemo_platform.types.inference.model_deployment import ModelDeployment
from nemo_platform.types.inference.model_deployment_config import ModelDeploymentConfig
from nemo_platform.types.models.model_entity import ModelEntity
from nmp.core.models.app import ModelWeightsType
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import (
    LOG_MAX_CHARS,
    LOG_TAIL_LINES,
    DeploymentConfigView,
    format_duration,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig

logger = getLogger(__name__)

POD_EVENT_TO_MESSAGE_MAP = {
    "startup probe failed": "Waiting for pod to finish startup",
}


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


class BaseReconciler(ABC):
    """Reconciles desired deployment state against actual backend resources.

    Subclasses talk only to Kubernetes (their own injected API clients). The
    shared status helpers below read the Deployment/pods/events that BOTH the
    operator path and the direct-emission path ultimately produce.
    """

    def __init__(
        self,
        k8s_client_: k8s_client.ApiClient,
        backend_config: K8sNimOperatorConfig,
        k8s_namespace: str,
    ) -> None:
        self._k8s_client = k8s_client_
        self._backend_config = backend_config
        self._k8s_namespace = k8s_namespace

    # ------------------------------------------------------------------
    # Reconciler interface
    # ------------------------------------------------------------------

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
    async def get_status_orphan(self, deployment: ModelDeployment, resource_name: str) -> DeploymentStatusUpdate:
        """Project status without a config (orphan-reconciliation paths).

        Same as :meth:`get_status` but for callers that lack a
        ``ModelDeploymentConfig`` (e.g. orphan reconciliation). Reconcilers MUST
        NOT advance creation here: with no config they cannot compile a serving
        spec, so they degrade to reporting the current phase.
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

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _get_host_url(self, resource_name: str) -> str:
        """Generate the Kubernetes service host URL for a deployment."""
        return f"http://{resource_name}.{self._k8s_namespace}.svc.cluster.local:8000"

    # Idempotent, 404-tolerant single-object delete (shared by both reconcilers)

    def _delete_one(self, delete_fn, kind: str, obj_name: str) -> Optional[str]:
        """Delete a single namespaced object by name, tolerating "already gone".

        Teardown deletes every resource type by name (no engine detection): this is
        idempotent and self-heals partial-deletion states. A 404 (object absent) is
        success. Any other failure is logged concisely (no stack trace) and
        returned as a short error string so the caller can aggregate and surface it
        (we must NOT mark a deployment DELETED if cluster resources may remain).
        """
        try:
            delete_fn(name=obj_name, namespace=self._k8s_namespace)
            logger.info(f"Deleted {kind} {self._k8s_namespace}/{obj_name}")
            return None
        except (k8s_client.exceptions.ApiException, k8s_dynamic_exceptions.NotFoundError) as e:
            # NotFound (typed status 404 or dynamic NotFoundError) -> already gone.
            if isinstance(e, k8s_dynamic_exceptions.NotFoundError) or getattr(e, "status", None) == 404:
                logger.debug(f"{kind} {obj_name} not found, already deleted")
                return None
            return self._classify_delete_error(e, kind, obj_name)
        except k8s_dynamic_exceptions.ForbiddenError as e:
            return self._classify_delete_error(e, kind, obj_name)

    @staticmethod
    def _classify_delete_error(e: Exception, kind: str, obj_name: str) -> str:
        """Concise, human-readable delete failure (no stack trace) for aggregation."""
        status = getattr(e, "status", None)
        is_forbidden = status == 403 or isinstance(e, k8s_dynamic_exceptions.ForbiddenError)
        if is_forbidden:
            # With the models ServiceAccount RBAC in place this should not happen;
            # if it does, the SA is missing delete on this resource type.
            msg = f"forbidden to delete {kind} {obj_name} (ServiceAccount lacks RBAC)"
            logger.error(msg)
            return msg
        msg = f"error deleting {kind} {obj_name}: {status or type(e).__name__}"
        logger.warning(msg)
        return msg

    # Pod log fetching and pod lookup (best-effort diagnostics)

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

    # Crash loop and pending timeout error builders

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

    # Pod status helpers

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
