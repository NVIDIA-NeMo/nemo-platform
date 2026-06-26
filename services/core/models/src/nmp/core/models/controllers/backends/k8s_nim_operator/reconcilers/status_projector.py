# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Engine-agnostic Kubernetes status projection.

Both reconcilers (operator-driven and direct-emission) ultimately observe the
same underlying Kubernetes objects -- a Deployment, its pods, and their events --
when reporting status. :class:`StatusProjector` owns that shared read-side logic
(pod log fetch, crash-loop detection, pod-status drill-down, the host URL, and
the PENDING-timeout / crash-loop error builders) so it can be *composed* into a
reconciler rather than inherited.

It talks only to Kubernetes via an injected ``ApiClient`` and never mutates
cluster state -- it just projects what it sees into a
:class:`DeploymentStatusUpdate`.
"""

from logging import getLogger
from typing import Any, Dict

from kubernetes import client as k8s_client
from nmp.core.models.controllers.backends.backends import DeploymentStatusUpdate
from nmp.core.models.controllers.backends.common import (
    LOG_MAX_CHARS,
    LOG_TAIL_LINES,
    format_duration,
)
from nmp.core.models.controllers.backends.k8s_nim_operator.config import K8sNimOperatorConfig

logger = getLogger(__name__)

# Maximum length of a recent-event message surfaced in ``status_message``. The
# value is persisted as the deployment's status and shown in the UI/CLI status
# history, so we cap it to keep history entries readable (not a protocol limit).
MAX_EVENT_MESSAGE_CHARS = 200

POD_EVENT_TO_MESSAGE_MAP = {
    "startup probe failed": "Waiting for pod to finish startup",
}


class StatusProjector:
    """Reads a Deployment + its pods/events and projects a status update.

    Engine-agnostic: composed into both reconcilers (and used directly by the
    ServiceBackend to enforce the PENDING-timeout policy).
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

    def host_url(self, resource_name: str) -> str:
        """Generate the Kubernetes service host URL for a deployment."""
        return f"http://{resource_name}.{self._k8s_namespace}.svc.cluster.local:8000"

    # Pod log fetching and pod lookup (best-effort diagnostics)

    def fetch_pod_logs(self, pod_name: str) -> str:
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

    def find_pod_name(self, resource_name: str) -> str | None:
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

    def build_pending_timeout_error(
        self,
        resource_name: str,
        elapsed: float,
        pod_name: str | None,
    ) -> DeploymentStatusUpdate:
        """Build ERROR status update for a PENDING timeout."""
        error_stack = self.fetch_pod_logs(pod_name) if pod_name else ""
        kubectl_target = pod_name if pod_name else f"deployment/{resource_name}"
        status_msg = (
            f"Deployment timed out after {format_duration(elapsed)} waiting for NIM "
            f"to pass health checks (timeout: {format_duration(self._backend_config.pending_timeout_seconds)}).\n\n"
            f"Inspect the model deployment's pod logs with:\n"
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

    def build_crash_loop_error(
        self,
        resource_name: str,
        pod_name: str,
        restart_count: int,
    ) -> DeploymentStatusUpdate:
        """Build ERROR status update for a crash loop."""
        error_stack = self.fetch_pod_logs(pod_name)
        status_msg = (
            f"Deployment entered crash loop after {restart_count} container restarts "
            f"(max: {self._backend_config.max_restart_count}).\n\n"
            f"Inspect the model deployment's pod logs with:\n"
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

    def check_crash_loop(self, pod: k8s_client.V1Pod, resource_name: str) -> DeploymentStatusUpdate | None:
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
                    return self.build_crash_loop_error(resource_name, pod_name, restart_count)
                else:
                    logger.debug(
                        "Pod has restarts above threshold but is not in waiting state",
                        extra={"pod": pod_name, "container_index": idx, "restart_count": restart_count},
                    )

        logger.debug("Crash loop check complete, no crash loop detected", extra={"pod": pod_name})
        return None

    def pod_status_from_deployment(self, resource_name: str) -> DeploymentStatusUpdate:
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

            crash_result = self.check_crash_loop(pod, resource_name)
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

            if len(message) > MAX_EVENT_MESSAGE_CHARS:
                message = message[: MAX_EVENT_MESSAGE_CHARS - 3] + "..."

            status_msg = self._with_restart_info(f"{reason}: {message}", restart_count)
            return DeploymentStatusUpdate(status="PENDING", status_message=status_msg, host_url=None)

        except Exception as e:
            logger.warning(f"Failed to get pod status for deployment {resource_name}: {e}")
            return DeploymentStatusUpdate(status="PENDING", status_message="Waiting for k8s deployment", host_url=None)
