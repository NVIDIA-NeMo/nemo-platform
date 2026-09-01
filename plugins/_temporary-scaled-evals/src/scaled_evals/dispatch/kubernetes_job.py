# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Launch one durable Kubernetes Job for each evaluation execution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scaled_evals.api.repositories.evaluation_repository import EvaluationRepository
from scaled_evals.dispatch.worker import (
    _LIFECYCLE_TIMEOUT_GRACE_SECONDS,
    _default_connect,
    _profile_lifecycle_timeout_seconds,
    _retry_delay_seconds,
    snapshot_agent_timeout_floor,
)
from scaled_evals.models.gym_identity import (
    gym_run_identity,
    is_snapshot_backed,
    snapshot_evaluation,
)

_TOKEN = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
_CA = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
_NAMESPACE = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
_GYM_RUNTIME = "gym_sandbox_opensandbox"
_DEFAULT_ACTIVE_DEADLINE_SECONDS = 7200
_DEFAULT_FINALIZATION_GRACE_SECONDS = 900
_REPLACED_IDENTITY_ENV = {
    "GYM_RUNNER_MODE",
    "GYM_RUNNER_IMAGE",
    "GYM_RUNNER_IMAGE_DIGEST",
    "GYM_SOURCE_REVISION",
    "GYM_PACKAGE_VERSION",
    "SCALED_EVALS_IMAGE_REF",
    "SCALED_EVALS_IMAGE_DIGEST",
}
_REMOVED_COMPOSITE_IDENTITY_ENV = {
    "SCALED_EVALS_CI_PIPELINE_ID",
    "SCALED_EVALS_CI_JOB_ID",
    "SCALED_EVALS_SIGNATURE_REF",
    "SCALED_EVALS_SIGNATURE_DIGEST",
    "SCALED_EVALS_SIGNATURE_AUDIT_ID",
}


@dataclass(frozen=True)
class GymJobConfig:
    image: str
    digest: str
    source_revision: str
    package_version: str | None
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str
    shm_size: str


@dataclass(frozen=True)
class RunnerJobResources:
    cpu_request: str
    cpu_limit: str
    memory_request: str
    memory_limit: str


def evaluation_job_active_deadline_seconds(
    row: Mapping[str, Any],
    *,
    configured_floor: int,
    finalization_grace: int,
) -> int:
    """Keep the outer Job alive across every sequential trial wave."""
    if configured_floor <= 0:
        raise ValueError("configured Kubernetes Job deadline floor must be positive")
    if finalization_grace < 0:
        raise ValueError("Kubernetes Job finalization grace must be non-negative")
    lifecycle_timeout = _profile_lifecycle_timeout_seconds(row)
    if lifecycle_timeout is None:
        # The row carries profile ids, not profile config, so fall back to the
        # sandbox budget a benchmark variant guarantees for the agent.
        agent_floor = snapshot_agent_timeout_floor(row)
        if agent_floor is None:
            return configured_floor
        lifecycle_timeout = agent_floor + _LIFECYCLE_TIMEOUT_GRACE_SECONDS
    evaluation = snapshot_evaluation(row)
    n_attempts = _positive_trial_count(evaluation.get("n_attempts"), field="n_attempts")
    parallelism = _positive_trial_count(evaluation.get("parallelism"), field="parallelism")
    trial_waves = math.ceil(n_attempts / parallelism)
    return max(
        configured_floor,
        math.ceil(trial_waves * lifecycle_timeout + finalization_grace),
    )


def _positive_trial_count(value: object, *, field: str) -> int:
    """Return a validated persisted trial count, defaulting legacy omissions to one."""
    if value is None:
        return 1
    if isinstance(value, bool):
        raise ValueError(f"evaluation {field} must be a positive integer")
    try:
        count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"evaluation {field} must be a positive integer") from exc
    if count <= 0:
        raise ValueError(f"evaluation {field} must be a positive integer")
    return count


class KubernetesEvaluationJobLauncher:
    """Clone the current worker pod into an independently owned evaluation Job."""

    def __init__(self) -> None:
        host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self.base_url = f"https://{host}:{port}"
        self.namespace = _NAMESPACE.read_text(encoding="utf-8").strip()
        self.pod_name = os.environ["HOSTNAME"]
        self.token = _TOKEN.read_text(encoding="utf-8").strip()
        self.context = ssl.create_default_context(cafile=str(_CA))

    def launch(self, evaluation_id: str) -> None:
        with _default_connect() as conn:
            row = EvaluationRepository(conn).load_for_dispatch(evaluation_id)
        if row is None:
            raise RuntimeError(f"evaluation not found for Kubernetes Job launch: {evaluation_id}")
        execution_number = int(row.get("current_execution") or 1)
        name = evaluation_job_name(evaluation_id, execution_number=execution_number)
        gym = gym_job_config(row)
        pod = self._request(
            "GET",
            f"/api/v1/namespaces/{_quote(self.namespace)}/pods/{_quote(self.pod_name)}",
        )
        body = build_job_manifest(
            pod,
            evaluation_id=evaluation_id,
            execution_number=execution_number,
            name=name,
            active_deadline_seconds=evaluation_job_active_deadline_seconds(
                row,
                configured_floor=int(
                    os.getenv(
                        "DISPATCH_JOB_ACTIVE_DEADLINE_SECONDS",
                        str(_DEFAULT_ACTIVE_DEADLINE_SECONDS),
                    )
                ),
                finalization_grace=int(
                    os.getenv(
                        "DISPATCH_JOB_FINALIZATION_GRACE_SECONDS",
                        str(_DEFAULT_FINALIZATION_GRACE_SECONDS),
                    )
                ),
            ),
            ttl_seconds=int(os.getenv("DISPATCH_JOB_TTL_SECONDS", "86400")),
            backoff_limit=int(os.getenv("DISPATCH_JOB_BACKOFF_LIMIT", "0")),
            runner_resources=RunnerJobResources(
                cpu_request=os.getenv("DISPATCH_JOB_CPU_REQUEST", "50m"),
                cpu_limit=os.getenv("DISPATCH_JOB_CPU_LIMIT", "1"),
                memory_request=os.getenv("DISPATCH_JOB_MEMORY_REQUEST", "256Mi"),
                memory_limit=os.getenv("DISPATCH_JOB_MEMORY_LIMIT", "1Gi"),
            ),
            gym=gym,
        )
        try:
            created = self._request(
                "POST",
                f"/apis/batch/v1/namespaces/{_quote(self.namespace)}/jobs",
                body,
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 409:
                raise
            created = self._request(
                "GET",
                f"/apis/batch/v1/namespaces/{_quote(self.namespace)}/jobs/{_quote(name)}",
            )
        uid = str((created.get("metadata") or {}).get("uid") or "")
        with _default_connect() as conn:
            EvaluationRepository(conn).record_dispatch_job(
                evaluation_id,
                execution_number=execution_number,
                name=name,
                uid=uid,
            )

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode()
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        with urllib.request.urlopen(  # noqa: S310 - fixed in-cluster Kubernetes API
            request, context=self.context, timeout=15
        ) as response:
            payload = response.read().decode("utf-8", errors="replace")
            return json.loads(payload) if payload else {}

    def reconcile_one(self, *, worker_id: str) -> bool:
        """Reconcile one leased outer Job without duplicating worker inspection."""
        from scaled_evals.api.settings import settings

        stale_seconds = settings.dispatch_job_reconcile_stale_seconds
        with _default_connect() as conn:
            repo = EvaluationRepository(conn)
            row = repo.claim_stale_dispatch_job(
                stale_seconds=stale_seconds,
                claim_timeout=max(stale_seconds, 60.0),
                worker_id=worker_id,
            )
        if row is None:
            return False
        name = str(row["dispatch_job_name"])
        execution_number = int(row.get("current_execution") or 1)
        try:
            job = self._request(
                "GET",
                f"/apis/batch/v1/namespaces/{_quote(self.namespace)}/jobs/{_quote(name)}",
            )
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                self._release_reconcile_claim(row, worker_id=worker_id)
                return False
            failure_code = "runner_disappeared"
            detail = f"evaluation Kubernetes Job {name} disappeared before terminal handoff"
        else:
            terminal = _terminal_job_condition(job)
            if terminal is None:
                self._release_reconcile_claim(row, worker_id=worker_id)
                return False
            failure_code, detail = self._job_failure_detail(name, job, terminal)
        with _default_connect() as conn:
            outcome = EvaluationRepository(conn).record_dispatch_job_infrastructure_failure(
                row["id"],
                execution_number=execution_number,
                dispatch_job_name=name,
                reconcile_worker_id=worker_id,
                failure_code=failure_code,
                detail=detail,
                retry_delay_seconds=_retry_delay_seconds(row["id"], execution_number),
            )
        return outcome is not None

    def _release_reconcile_claim(self, row: dict[str, Any], *, worker_id: str) -> None:
        with _default_connect() as conn:
            EvaluationRepository(conn).release_dispatch_reconcile_claim(
                row["id"],
                execution_number=int(row.get("current_execution") or 1),
                dispatch_job_name=str(row["dispatch_job_name"]),
                worker_id=worker_id,
            )

    def _job_failure_detail(
        self,
        name: str,
        job: dict[str, Any],
        terminal: dict[str, Any],
    ) -> tuple[str, str]:
        pod_reason = None
        pod_message = None
        try:
            pods = self._request(
                "GET",
                f"/api/v1/namespaces/{_quote(self.namespace)}/pods?labelSelector={_quote(f'job-name={name}')}",
            )
            pod_reason, pod_message = _strongest_pod_failure(pods)
        except Exception:  # noqa: BLE001 - Job condition remains durable evidence
            pass
        condition_type = str(terminal.get("type") or "Failed")
        condition_reason = str(terminal.get("reason") or condition_type)
        reason = pod_reason or condition_reason
        failure_code = _runner_failure_code(reason, condition_type=condition_type)
        detail = f"evaluation Kubernetes Job {name} reached {condition_type} before database terminal handoff: {reason}"
        message = pod_message or str(terminal.get("message") or "").strip()
        if message:
            detail = f"{detail}: {message}"
        return failure_code, detail


def evaluation_job_name(evaluation_id: str, *, execution_number: int = 1) -> str:
    if execution_number < 1:
        raise ValueError("execution_number must be positive")
    digest = hashlib.sha256(f"{evaluation_id}:{execution_number}".encode()).hexdigest()[:20]
    return f"scaled-evals-eval-{digest}"


def build_job_manifest(
    pod: dict[str, Any],
    *,
    evaluation_id: str,
    execution_number: int = 1,
    name: str,
    active_deadline_seconds: int,
    ttl_seconds: int,
    backoff_limit: int,
    runner_resources: RunnerJobResources | None = None,
    gym: GymJobConfig | None = None,
) -> dict[str, Any]:
    """Copy runtime wiring from the immutable worker pod into a standalone Job."""
    pod_spec = copy.deepcopy(pod["spec"])
    for key in ("nodeName", "schedulerName", "terminationGracePeriodSeconds"):
        pod_spec.pop(key, None)
    pod_spec["restartPolicy"] = "Never"
    containers = pod_spec["containers"]
    if len(containers) != 1:
        raise RuntimeError("dispatch worker pod must contain exactly one application container")
    container = containers[0]
    container["name"] = "evaluation-runner"
    container["command"] = ["scaled-evals-dispatch-worker"]
    container.pop("args", None)
    if runner_resources is not None:
        container["resources"] = {
            "requests": {
                "cpu": runner_resources.cpu_request,
                "memory": runner_resources.memory_request,
            },
            "limits": {
                "cpu": runner_resources.cpu_limit,
                "memory": runner_resources.memory_limit,
            },
        }
    env = [
        item
        for item in container.get("env", [])
        if item.get("name") not in {"SCALED_EVALS_EVALUATION_ID", "SCALED_EVALS_EXECUTION_NUMBER"}
    ]
    env.extend(
        [
            {"name": "SCALED_EVALS_EVALUATION_ID", "value": evaluation_id},
            {"name": "SCALED_EVALS_EXECUTION_NUMBER", "value": str(execution_number)},
        ]
    )
    if gym is not None:
        container["image"] = gym.image
        env = [item for item in env if item.get("name") not in _REPLACED_IDENTITY_ENV | _REMOVED_COMPOSITE_IDENTITY_ENV]
        env.extend(
            {"name": name, "value": value}
            for name, value in (
                ("GYM_RUNNER_MODE", "process"),
                ("GYM_RUNNER_IMAGE", gym.image),
                ("GYM_RUNNER_IMAGE_DIGEST", gym.digest),
                ("GYM_SOURCE_REVISION", gym.source_revision),
                ("GYM_PACKAGE_VERSION", gym.package_version or ""),
                ("SCALED_EVALS_IMAGE_REF", gym.image),
                ("SCALED_EVALS_IMAGE_DIGEST", gym.digest),
            )
        )
        container["resources"] = {
            "requests": {"cpu": gym.cpu_request, "memory": gym.memory_request},
            "limits": {"cpu": gym.cpu_limit, "memory": gym.memory_limit},
        }
        gym_volume_names = {"gym-cache", "gym-shm"}
        mounts = [item for item in container.get("volumeMounts", []) if item.get("name") not in gym_volume_names]
        mounts.extend(
            (
                {"name": "gym-cache", "mountPath": "/opt/gym/cache"},
                {"name": "gym-shm", "mountPath": "/dev/shm"},
            )
        )
        container["volumeMounts"] = mounts
        volumes = [item for item in pod_spec.get("volumes", []) if item.get("name") not in gym_volume_names]
        volumes.extend(
            (
                {"name": "gym-cache", "emptyDir": {}},
                {
                    "name": "gym-shm",
                    "emptyDir": {"medium": "Memory", "sizeLimit": gym.shm_size},
                },
            )
        )
        pod_spec["volumes"] = volumes
    container["env"] = env
    labels = {
        "app.kubernetes.io/name": "scaled-evals",
        "app.kubernetes.io/component": "evaluation-runner",
        "scaled-evals.nvidia.com/evaluation-job": "true",
    }
    pod_annotations = {
        # A replacement pod cannot resume the runner's in-memory agent and sandbox session.
        "cluster-autoscaler.kubernetes.io/safe-to-evict": "false",
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name,
            "labels": labels,
            "annotations": {"scaled-evals.nvidia.com/evaluation-id": evaluation_id},
        },
        "spec": {
            "activeDeadlineSeconds": active_deadline_seconds,
            # A process-backed Gym run cannot resume in a replacement pod, and
            # retrying after sandbox creation can duplicate remote resources.
            "backoffLimit": 0 if gym is not None else backoff_limit,
            "ttlSecondsAfterFinished": ttl_seconds,
            "template": {
                "metadata": {"labels": labels, "annotations": pod_annotations},
                "spec": pod_spec,
            },
        },
    }


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _terminal_job_condition(job: Mapping[str, Any]) -> dict[str, Any] | None:
    conditions = (job.get("status") or {}).get("conditions") or []
    return next(
        (
            dict(item)
            for item in conditions
            if item.get("status") == "True" and item.get("type") in {"Failed", "Complete"}
        ),
        None,
    )


def _strongest_pod_failure(pods: Mapping[str, Any]) -> tuple[str | None, str | None]:
    candidates: list[tuple[str, str | None]] = []
    for pod in pods.get("items") or []:
        status = pod.get("status") or {}
        if status.get("reason"):
            candidates.append((str(status["reason"]), str(status.get("message") or "") or None))
        for field in ("initContainerStatuses", "containerStatuses"):
            for container in status.get(field) or []:
                terminated = (container.get("state") or {}).get("terminated") or {}
                if not terminated:
                    continue
                reason = str(terminated.get("reason") or "")
                exit_code = terminated.get("exitCode")
                if not reason and exit_code is not None:
                    reason = f"ExitCode{exit_code}"
                message = str(terminated.get("message") or "").strip() or None
                if reason:
                    candidates.append((reason, message))
    priority = {
        "OOMKilled": 0,
        "Evicted": 1,
        "NodeLost": 2,
        "DeadlineExceeded": 3,
    }
    if not candidates:
        return None, None
    return min(candidates, key=lambda candidate: priority.get(candidate[0], 10))


def _runner_failure_code(reason: str, *, condition_type: str) -> str:
    normalized = reason.lower()
    if "oomkilled" in normalized:
        return "runner_oomkilled"
    if "evicted" in normalized:
        return "runner_evicted"
    if "nodelost" in normalized or "node lost" in normalized:
        return "runner_node_lost"
    if "deadlineexceeded" in normalized or "deadline exceeded" in normalized:
        return "runner_deadline_exceeded"
    if condition_type == "Complete":
        return "runner_handoff_lost"
    return "runner_disappeared"


def gym_job_config(row: dict[str, Any]) -> GymJobConfig | None:
    evaluation = snapshot_evaluation(row)
    runtime = str(evaluation.get("runtime") or row.get("runtime") or "")
    if runtime != _GYM_RUNTIME:
        return None
    if not is_snapshot_backed(row):
        raise RuntimeError("hosted Gym evaluation requires an immutable execution snapshot")
    image_ref = str(evaluation.get("runner_image_ref") or "").strip()
    digest = str(evaluation.get("runner_image_digest") or "").strip().lower()
    if not image_ref or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
        raise RuntimeError("hosted Gym evaluation requires a snapshot-pinned sha256 runner image")
    if "@" in image_ref:
        repository, reference_digest = image_ref.rsplit("@", 1)
        if reference_digest.lower() != digest:
            raise RuntimeError("Gym runner image reference and snapshot digest do not match")
    else:
        last_slash = image_ref.rfind("/")
        last_colon = image_ref.rfind(":")
        repository = image_ref[:last_colon] if last_colon > last_slash else image_ref
    identity = gym_run_identity(row) or {}
    source_revision = str(identity.get("source_revision") or "")
    if re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", source_revision) is None:
        raise RuntimeError("hosted Gym evaluation snapshot is missing Gym source revision")
    from scaled_evals.api.settings import settings

    return GymJobConfig(
        image=f"{repository}@{digest}",
        digest=digest,
        source_revision=source_revision,
        package_version=str(identity.get("package_version") or "") or None,
        cpu_request=settings.gym_job_cpu_request,
        cpu_limit=settings.gym_job_cpu_limit,
        memory_request=settings.gym_job_memory_request,
        memory_limit=settings.gym_job_memory_limit,
        shm_size=settings.gym_job_shm_size,
    )
