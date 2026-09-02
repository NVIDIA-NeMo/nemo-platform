# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Per-evaluation Switchyard provisioning for dispatch.

The control plane owns one Switchyard Deployment + Service per evaluation when
``switchyard_profile_id`` is present. This module renders the Kubernetes
resources, applies/deletes them through ``kubectl``, and writes redacted
Switchyard artifacts into the evaluation artifact tree.

The Remote Harbor contract is the reference shape:

* OpenAI/Codex-wire clients receive ``<service>/v1`` and a placeholder
  ``OPENAI_API_KEY=switchyard``.
* Anthropic/Claude-wire clients receive ``<service>`` without ``/v1`` and
  placeholder Anthropic auth values.
* Upstream provider credentials live only in the Switchyard Secret.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from scaled_evals.api.redaction import redact_secret_text
from scaled_evals.api.settings import settings
from scaled_evals.dispatch.inference_headers import (
    inference_header_runner_env,
    with_default_inference_priority,
)
from scaled_evals.dispatch.kubectl import KubectlResult, execute_kubectl
from scaled_evals.models.runtime import SwitchyardLease

SWITCHYARD_ARTIFACT_DIR = "switchyard"
ROUTES_FILE_NAME = "routes.yaml"
MANIFEST_FILE_NAME = "k8s-manifest.redacted.json"
LEASE_FILE_NAME = "lease.json"
STATUS_FILE_NAME = "status.json"
LOG_FILE_NAME = "switchyard.log"
PREVIOUS_LOG_FILE_NAME = "switchyard.previous.log"
EVENTS_FILE_NAME = "events.json"
ROUTING_STATS_FILE_NAME = "routing_stats_final.json"
ROUTING_LOG_FILE_PATH = "/var/lib/switchyard/routing_requests.jsonl"
ROUTING_SESSION_STATS_PATH = "/v1/routing/session-stats"

_AZURE_CLIENT_ID_ENV = "AZURE_CLIENT_ID"
_AZURE_TENANT_ID_ENV = "AZURE_TENANT_ID"
_AZURE_FEDERATED_TOKEN_FILE_ENV = "AZURE_FEDERATED_TOKEN_FILE"
_AZURE_FEDERATED_TOKEN_PATH = "/var/run/secrets/azure/token"
_AZURE_TOKEN_AUDIENCE = "api://AzureADTokenExchange"
_DEFAULT_AZURE_AUTHORITY_HOST = "https://login.microsoftonline.com/"
_AZURE_ENTRA_TOKEN_ENV = "AZURE_ENTRA_TOKEN"
_AZURE_TOKEN_SCOPE = "https://ai.azure.com/.default"

_DNS_RE = re.compile(r"[^a-z0-9-]+")
_ENV_REF_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:-[^}]*)?\}")
_SECRET_ENV_RE = re.compile(r"(api[_-]?key|auth[_-]?token|token|secret|password)$", re.I)
_DEFAULT_SECRET_KEYS = (
    "OPENAI_API_KEY",
    "NVIDIA_API_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "NGC_INFERENCE_API_KEY",
    "POLICY_API_KEY",
)
_ROUTING_TASK_HEADER = "x-switchyard-intake-task"
_ROUTING_SESSION_HEADER = "proxy_x_session_id"
_RESERVED_BINDING_ENV = frozenset(
    {
        "PATH",
        "HOME",
        "KUBECONFIG",
        "PYTHONPATH",
        "PYTHONHOME",
        "LD_PRELOAD",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
        "NVIDIA_BASE_URL",
        "POLICY_BASE_URL",
        "SWITCHYARD_API_KEY",
    }
)
_DEFAULT_RUN_AS_USER = 1000


class SwitchyardProvisionError(RuntimeError):
    """Managed Switchyard provisioning failed after diagnostics were captured."""


class SwitchyardReadinessError(SwitchyardProvisionError):
    """Managed Switchyard did not become ready before its bounded timeout."""


class SwitchyardProfileConfig(BaseModel):
    """Non-secret Switchyard profile config stored in ``config_profiles.config``."""

    model_config = ConfigDict(extra="allow")

    mode: Literal["managed", "external"] = "managed"
    endpoint: str | None = None
    image: str | None = None
    switchyard_image: str | None = None
    image_digest: str | None = None
    source_project: str | None = None
    source_ref: str | None = None
    source_commit: str | None = None
    context_path: str | None = None
    dockerfile_path: str | None = None
    dockerfile_sha256: str | None = None
    context_hash: str | None = None
    namespace: str | None = None
    switchyard_namespace: str | None = None
    name_prefix: str | None = "switchyard"
    switchyard_name_prefix: str | None = None
    port: int = Field(default=4000, ge=1, le=65535)
    replicas: int = Field(default=1, ge=1, le=16)
    inbound: Literal["openai", "anthropic", "both"] = "openai"
    # Switchyard owns the semantics of this declaration. Scaled-evals records
    # it for posture/provenance but does not reinterpret routing policy.
    book_mode: Literal["closed", "open"] | None = None
    switchyard_inbound: Literal["openai", "anthropic", "both"] | None = None
    routing_profiles_yaml: str | None = None
    routing_profiles_yml: str | None = None
    switchyard_routing_profiles_yaml: str | None = None
    switchyard_routing_profiles_yml: str | None = None
    routing_profiles: dict[str, Any] | None = None
    command: list[str] | None = None
    args: list[str] | None = None
    image_pull_policy: str = "IfNotPresent"
    image_pull_secrets: list[str] = Field(default_factory=list)
    service_account_name: str | None = None
    upstream_base_url: str = Field(default_factory=lambda: settings.nvidia_inference_base_url)
    env: dict[str, str] = Field(default_factory=dict)
    credential_bindings: dict[str, list[str]] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(
        default_factory=lambda: {
            "requests": {"cpu": "250m", "memory": "512Mi"},
            "limits": {"cpu": "2", "memory": "2Gi"},
        }
    )
    readiness_path: str = "/health"
    readiness_timeout_seconds: int = Field(default=900, ge=1, le=1800)
    run_as_user: int | None = Field(default=None, ge=1)
    routing_stats_path: str = "/v1/routing/stats"
    routing_stats_max_bytes: int = Field(default=1_048_576, ge=1, le=16_777_216)
    drain_seconds: float | None = Field(default=None, ge=0)
    capture_logs: bool = True
    sandbox_egress_network_policy: bool = True

    @model_validator(mode="after")
    def _mode_fields(self) -> SwitchyardProfileConfig:
        if self.mode == "external" and not self.endpoint:
            raise ValueError("external switchyard profile requires endpoint")
        if self.mode == "external":
            managed_only = {
                "image",
                "switchyard_image",
                "namespace",
                "switchyard_namespace",
                "routing_profiles_yaml",
                "routing_profiles_yml",
                "switchyard_routing_profiles_yaml",
                "switchyard_routing_profiles_yml",
                "routing_profiles",
                "command",
                "args",
                "image_pull_policy",
                "image_pull_secrets",
                "service_account_name",
                "upstream_base_url",
                "env",
                "credential_bindings",
                "resources",
                "readiness_path",
                "readiness_timeout_seconds",
                "run_as_user",
                "routing_stats_path",
                "routing_stats_max_bytes",
                "replicas",
                "drain_seconds",
                "capture_logs",
                "sandbox_egress_network_policy",
            }
            supplied = sorted(self.model_fields_set & managed_only)
            if supplied:
                raise ValueError("external switchyard profile contains managed-only field(s): " + ", ".join(supplied))
        if self.mode == "managed" and self.endpoint is not None:
            raise ValueError("endpoint is only valid for external switchyard profiles")
        binding_targets = {target for targets in self.credential_bindings.values() for target in targets}
        collisions = sorted(binding_targets & set(self.env))
        if collisions:
            raise ValueError("Switchyard credential target collides with profile env: " + collisions[0])
        return self

    @field_validator("command", "args", mode="before")
    @classmethod
    def _string_list(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("must be a list of strings")
        return value

    @field_validator("env", mode="before")
    @classmethod
    def _string_env(cls, value: Any) -> Any:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("env must be an object")
        return {str(key): str(item) for key, item in value.items()}

    @field_validator("credential_bindings", mode="before")
    @classmethod
    def _credential_bindings(cls, value: Any) -> dict[str, list[str]]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("credential_bindings must be a role-to-env mapping")
        normalized: dict[str, list[str]] = {}
        seen: set[str] = set()
        for raw_role, raw_targets in value.items():
            role = str(raw_role).strip()
            targets = [raw_targets] if isinstance(raw_targets, str) else raw_targets
            if not role or not isinstance(targets, list) or not targets:
                raise ValueError("credential_bindings roles require one or more env names")
            normalized_targets: list[str] = []
            for raw_target in targets:
                target = str(raw_target).strip()
                if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", target):
                    raise ValueError(f"invalid Switchyard credential target: {target!r}")
                if target in _RESERVED_BINDING_ENV or target.startswith("SCALED_EVALS_"):
                    raise ValueError(f"reserved Switchyard credential target: {target}")
                if target in seen:
                    raise ValueError(f"duplicate Switchyard credential target: {target}")
                seen.add(target)
                normalized_targets.append(target)
            normalized[role] = normalized_targets
        return normalized


@dataclass(frozen=True)
class SwitchyardRender:
    lease: SwitchyardLease
    apply_object: dict[str, Any]
    redacted_object: dict[str, Any]
    routing_profiles_text: str
    runner_env: dict[str, str]


KubectlRunner = Callable[[list[str], str | None], KubectlResult]


class SwitchyardProvisioner(Protocol):
    def provision(
        self,
        *,
        evaluation_id: str,
        profile_id: str,
        raw_config: Mapping[str, Any],
        credential_env: Mapping[str, str],
        artifact_root: Path,
        benchmark_run_id: str | None = None,
        persist_lease: Callable[[SwitchyardLease], None] | None = None,
    ) -> SwitchyardRender: ...

    def capture(
        self,
        lease: SwitchyardLease,
        artifact_root: Path,
        *,
        final: bool = False,
        session_ids: Sequence[str] = (),
    ) -> str | None: ...

    def ensure_ready(self, lease: SwitchyardLease) -> None: ...

    def delete(self, lease: SwitchyardLease, artifact_root: Path | None = None) -> None: ...


class KubectlSwitchyardProvisioner:
    """Provision per-run Switchyard resources through the local kubectl context."""

    def __init__(
        self,
        *,
        kubectl: str = "kubectl",
        context: str | None = None,
        namespace: str | None = None,
        image: str | None = None,
        image_pull_secrets: tuple[str, ...] = (),
        kube_insecure_skip_tls_verify: bool = False,
        drain_seconds: float | None = None,
        external_allowed_hosts: tuple[str, ...] = (),
        runner: KubectlRunner | None = None,
    ) -> None:
        self.kubectl = kubectl
        self.context = context
        self.namespace = namespace
        self.image = image
        self.image_pull_secrets = image_pull_secrets
        self.kube_insecure_skip_tls_verify = kube_insecure_skip_tls_verify
        self.drain_seconds = drain_seconds
        self.external_allowed_hosts = external_allowed_hosts
        self.runner = runner or _run_kubectl

    def provision(
        self,
        *,
        evaluation_id: str,
        profile_id: str,
        raw_config: Mapping[str, Any],
        credential_env: Mapping[str, str],
        artifact_root: Path,
        benchmark_run_id: str | None = None,
        persist_lease: Callable[[SwitchyardLease], None] | None = None,
    ) -> SwitchyardRender:
        config = SwitchyardProfileConfig.model_validate(raw_config or {})
        resolved_credential_env = dict(credential_env)
        if config.mode == "managed" and _wants_azure_workload_identity(config.env):
            resolved_credential_env[_AZURE_ENTRA_TOKEN_ENV] = _mint_azure_entra_token(config.env)
        render = render_switchyard(
            evaluation_id=evaluation_id,
            profile_id=profile_id,
            config=config,
            credential_env=resolved_credential_env,
            artifact_root=artifact_root,
            namespace=self.namespace,
            image=self.image,
            default_image_pull_secrets=self.image_pull_secrets,
            drain_seconds=self.drain_seconds,
            benchmark_run_id=benchmark_run_id,
            external_allowed_hosts=self.external_allowed_hosts,
        )
        write_switchyard_artifacts(render, artifact_root)
        # Persist the deterministic resource identity before the first cluster
        # mutation. Campaign cancellation/finalization can then always issue an
        # idempotent delete, including while apply or readiness is still in
        # flight. The callback is fenced by the campaign provisioning claim.
        if persist_lease is not None:
            persist_lease(render.lease)
        if render.lease.mode == "external":
            return render
        payload = json.dumps(render.apply_object, separators=(",", ":"))
        # Server-side admission still validates the generated objects. Disabling
        # kubectl's client-side OpenAPI fetch keeps OpenShift-style targets with custom
        # CA wiring from failing before the request reaches the API server.
        result = self._kubectl(
            ["apply", "--validate=false", "-f", "-"],
            namespace=None,
            input_text=payload,
        )
        if result.returncode != 0:
            diagnostic_note = None
            try:
                diagnostic_note = self.capture(render.lease, artifact_root)
            except Exception as exc:  # noqa: BLE001 - rollback must still run
                diagnostic_note = f"switchyard diagnostic capture failed: {exc}"
            rollback = self._kubectl(
                [
                    "delete",
                    "deployment,service,configmap,secret,networkpolicy",
                    "-l",
                    _label_selector(render.lease),
                    "--ignore-not-found=true",
                ],
                namespace=render.lease.namespace,
                input_text=None,
            )
            detail = f"switchyard apply failed: {result.stderr or result.stdout}"
            if diagnostic_note:
                detail += f"; {diagnostic_note}"
            if rollback.returncode != 0:
                detail += f"; rollback failed: {rollback.stderr or rollback.stdout}"
            raise SwitchyardProvisionError(detail)
        ready = self._kubectl(
            [
                "rollout",
                "status",
                f"deployment/{render.lease.name}",
                f"--timeout={config.readiness_timeout_seconds}s",
            ],
            namespace=render.lease.namespace,
            input_text=None,
        )
        if ready.returncode != 0:
            diagnostic_note = None
            try:
                diagnostic_note = self.capture(render.lease, artifact_root)
            except Exception as exc:  # noqa: BLE001 - rollback must still run
                diagnostic_note = f"switchyard diagnostic capture failed: {exc}"
            rollback = self._kubectl(
                [
                    "delete",
                    "deployment,service,configmap,secret,networkpolicy",
                    "-l",
                    _label_selector(render.lease),
                    "--ignore-not-found=true",
                ],
                namespace=render.lease.namespace,
                input_text=None,
            )
            detail = f"switchyard readiness failed: {ready.stderr or ready.stdout}"
            if diagnostic_note:
                detail += f"; {diagnostic_note}"
            if rollback.returncode != 0:
                detail += f"; rollback failed: {rollback.stderr or rollback.stdout}"
            raise SwitchyardReadinessError(detail)
        return render

    def capture(
        self,
        lease: SwitchyardLease,
        artifact_root: Path,
        *,
        final: bool = False,
        session_ids: Sequence[str] = (),
    ) -> str | None:
        root = _switchyard_artifact_root(artifact_root)
        root.mkdir(parents=True, exist_ok=True)
        if lease.mode == "external":
            (root / STATUS_FILE_NAME).write_text(
                json.dumps(
                    {
                        "mode": "external",
                        "endpoint_identity": lease.endpoint_identity,
                        "managed_resources": False,
                        "warning": lease.trust_warning,
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return None
        notes: list[str] = []

        resources = self._kubectl(
            [
                "get",
                *_switchyard_get_resource_refs(lease),
                "-o",
                "json",
            ],
            namespace=lease.namespace,
            input_text=None,
        )
        pods = self._kubectl(
            [
                "get",
                "pods",
                "-l",
                _label_selector(lease),
                "-o",
                "json",
            ],
            namespace=lease.namespace,
            input_text=None,
        )
        (root / STATUS_FILE_NAME).write_text(
            redact_secret_text(_switchyard_status_text(resources=resources, pods=pods)) + "\n",
            encoding="utf-8",
        )
        if resources.returncode != 0 or pods.returncode != 0:
            notes.append("switchyard status capture failed")

        pod_restarts = _switchyard_pod_restarts(pods)
        pod_names = [name for name, _restart_count in pod_restarts]
        if lease.inbound and lease.name:
            current_logs: list[str] = []
            current_log_failed = False
            log_targets = [f"pod/{name}" for name in pod_names] or [f"deployment/{lease.name}"]
            for target in log_targets:
                command = ["logs", target, "-c", "switchyard", "--tail=-1", "--timestamps=true"]
                if target.startswith("deployment/"):
                    command.append("--all-pods=true")
                logs = self._kubectl(command, namespace=lease.namespace, input_text=None)
                current_logs.append(f"--- {target} ---\n{logs.stdout or logs.stderr}".rstrip())
                current_log_failed = current_log_failed or logs.returncode != 0
            (root / LOG_FILE_NAME).write_text(
                redact_secret_text("\n".join(current_logs)).rstrip() + "\n",
                encoding="utf-8",
            )
            if current_log_failed:
                notes.append("switchyard log capture failed")

            previous_logs: list[str] = []
            previous_log_failed = False
            for pod_name, restart_count in pod_restarts:
                if restart_count < 1:
                    continue
                logs = self._kubectl(
                    [
                        "logs",
                        f"pod/{pod_name}",
                        "-c",
                        "switchyard",
                        "--previous",
                        "--tail=-1",
                        "--timestamps=true",
                    ],
                    namespace=lease.namespace,
                    input_text=None,
                )
                previous_logs.append(
                    (
                        f"--- pod/{pod_name} previous restart_count={restart_count} ---\n{logs.stdout or logs.stderr}"
                    ).rstrip()
                )
                previous_log_failed = previous_log_failed or logs.returncode != 0
            if not previous_logs:
                previous_logs.append("no restarted Switchyard containers observed")
            (root / PREVIOUS_LOG_FILE_NAME).write_text(
                redact_secret_text("\n".join(previous_logs)).rstrip() + "\n",
                encoding="utf-8",
            )
            if previous_log_failed:
                notes.append("switchyard previous log capture failed")

        event_results: dict[str, Any] = {}
        event_capture_failed = False
        for resource_name in dict.fromkeys([lease.name, *pod_names]):
            if not resource_name:
                continue
            events = self._kubectl(
                [
                    "get",
                    "events",
                    "--field-selector",
                    f"involvedObject.name={resource_name}",
                    "-o",
                    "json",
                ],
                namespace=lease.namespace,
                input_text=None,
            )
            event_results[resource_name] = _kubectl_json_or_text(events)
            event_capture_failed = event_capture_failed or events.returncode != 0
        (root / EVENTS_FILE_NAME).write_text(
            redact_secret_text(json.dumps(event_results, indent=2, sort_keys=True)) + "\n",
            encoding="utf-8",
        )
        if event_capture_failed:
            notes.append("switchyard event capture failed")

        if final:
            requested_session_ids = tuple(dict.fromkeys(value for value in session_ids if value))
            if requested_session_ids:
                sessions: dict[str, Any] = {}
                for session_id in requested_session_ids:
                    candidate_notes: list[str] = []
                    session_stats = self._capture_routing_stats(
                        lease,
                        session_id=session_id,
                        notes=candidate_notes,
                    )
                    if session_stats is None:
                        continue
                    if session_stats.get("session_id") != session_id:
                        notes.append(f"switchyard routing stats session mismatch for {session_id}")
                        continue
                    sessions[session_id] = session_stats
                parsed_stats: dict[str, Any] | None = {
                    "requested_session_ids": list(requested_session_ids),
                    "sessions": sessions,
                }
            else:
                parsed_stats = self._capture_routing_stats(lease, notes=notes)

            if parsed_stats is not None:
                serialized = json.dumps(parsed_stats, indent=2, sort_keys=True) + "\n"
                if len(serialized.encode()) > lease.routing_stats_max_bytes:
                    notes.append("switchyard routing stats exceeded size limit")
                else:
                    (root / ROUTING_STATS_FILE_NAME).write_text(
                        serialized,
                        encoding="utf-8",
                    )

        return "; ".join(notes) if notes else None

    def ensure_ready(self, lease: SwitchyardLease) -> None:
        """Verify a persisted managed lease still has reachable Kubernetes resources."""
        if lease.mode == "external":
            return
        if not lease.namespace or not lease.name or not lease.service_name:
            raise RuntimeError("managed Switchyard lease is missing Kubernetes resource identity")
        resources = self._kubectl(
            [
                "get",
                *_switchyard_get_resource_refs(lease),
                "-o",
                "name",
            ],
            namespace=lease.namespace,
            input_text=None,
        )
        if resources.returncode != 0:
            raise RuntimeError(f"switchyard resources are unavailable: {resources.stderr or resources.stdout}".strip())
        ready = self._kubectl(
            [
                "rollout",
                "status",
                f"deployment/{lease.name}",
                "--timeout=1s",
            ],
            namespace=lease.namespace,
            input_text=None,
        )
        if ready.returncode != 0:
            raise RuntimeError(f"switchyard deployment is not ready: {ready.stderr or ready.stdout}".strip())

    def delete(self, lease: SwitchyardLease, artifact_root: Path | None = None) -> None:
        if artifact_root is not None:
            with suppress(Exception):
                switchyard_root = _switchyard_artifact_root(artifact_root)
                status_path = switchyard_root / STATUS_FILE_NAME
                if not status_path.is_file():
                    stats_path = switchyard_root / ROUTING_STATS_FILE_NAME
                    self.capture(lease, artifact_root, final=not stats_path.is_file())
        if lease.mode == "external":
            return
        result = self._kubectl(
            [
                "delete",
                f"configmap/{lease.config_map_name}",
                f"secret/{lease.secret_name}",
                *_switchyard_get_resource_refs(lease),
                "--ignore-not-found=true",
            ],
            namespace=lease.namespace,
            input_text=None,
        )
        if result.returncode != 0:
            raise RuntimeError(f"switchyard delete failed: {result.stderr or result.stdout}")

    def _capture_routing_stats(
        self,
        lease: SwitchyardLease,
        *,
        notes: list[str],
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        query = f"?{urlencode({'session_id': session_id})}" if session_id is not None else ""
        path = ROUTING_SESSION_STATS_PATH if session_id is not None else lease.routing_stats_path
        result = self._kubectl(
            [
                "get",
                "--raw",
                (
                    f"/api/v1/namespaces/{lease.namespace}/services/"
                    f"http:{lease.service_name}:{lease.port}/proxy"
                    f"{path}{query}"
                ),
            ],
            namespace=None,
            input_text=None,
        )
        label = f" for session {session_id}" if session_id is not None else ""
        if result.returncode != 0:
            notes.append(f"switchyard routing stats capture failed{label}")
            return None
        if len(result.stdout.encode()) > lease.routing_stats_max_bytes:
            notes.append(f"switchyard routing stats exceeded size limit{label}")
            return None
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            notes.append(f"switchyard routing stats were not valid JSON{label}")
            return None
        if not isinstance(parsed, dict):
            notes.append(f"switchyard routing stats were not a JSON object{label}")
            return None
        return parsed

    def _kubectl(
        self,
        args: list[str],
        *,
        namespace: str | None,
        input_text: str | None,
    ) -> KubectlResult:
        command = [self.kubectl]
        if self.context:
            command.extend(["--context", self.context])
        if self.kube_insecure_skip_tls_verify:
            command.append("--insecure-skip-tls-verify=true")
        if namespace:
            command.extend(["-n", namespace])
        command.extend(args)
        return self.runner(command, input_text)


def build_switchyard_provisioner() -> KubectlSwitchyardProvisioner:
    return KubectlSwitchyardProvisioner(
        context=settings.switchyard_kube_context,
        namespace=settings.switchyard_namespace,
        image=settings.switchyard_image,
        image_pull_secrets=tuple(
            item.strip() for item in settings.switchyard_image_pull_secrets.split(",") if item.strip()
        ),
        kube_insecure_skip_tls_verify=settings.switchyard_kube_insecure_skip_tls_verify,
        drain_seconds=settings.switchyard_drain_seconds,
        external_allowed_hosts=tuple(
            item.strip() for item in settings.switchyard_external_allowed_hosts.split(",") if item.strip()
        ),
    )


def render_switchyard(
    *,
    evaluation_id: str,
    profile_id: str,
    config: SwitchyardProfileConfig,
    credential_env: Mapping[str, str],
    artifact_root: Path,
    namespace: str | None = None,
    image: str | None = None,
    default_image_pull_secrets: tuple[str, ...] = (),
    drain_seconds: float | None = None,
    benchmark_run_id: str | None = None,
    external_allowed_hosts: tuple[str, ...] = (),
) -> SwitchyardRender:
    if config.mode == "external":
        return _render_external_switchyard(
            evaluation_id=evaluation_id,
            profile_id=profile_id,
            config=config,
            credential_env=credential_env,
            external_allowed_hosts=external_allowed_hosts,
        )
    resolved_namespace = config.namespace or config.switchyard_namespace or namespace or "default"
    resolved_image = config.image or config.switchyard_image or image
    if not resolved_image:
        raise ValueError("switchyard profile requires image or SWITCHYARD_IMAGE")
    resolved_image_pull_secrets = list(dict.fromkeys((*default_image_pull_secrets, *config.image_pull_secrets)))

    name = _resource_name(
        config.switchyard_name_prefix or config.name_prefix or "switchyard",
        evaluation_id,
    )
    inbound = config.switchyard_inbound or config.inbound
    service_name = name
    config_map_name = f"{name}-routes"
    secret_name = f"{name}-secrets"
    network_policy_name = f"{name}-sandbox-egress"
    endpoint = f"http://{service_name}.{resolved_namespace}.svc.cluster.local:{config.port}"
    openai_base_url = f"{endpoint}/v1"
    anthropic_base_url = endpoint
    resolved_drain = (
        config.drain_seconds
        if config.drain_seconds is not None
        else drain_seconds
        if drain_seconds is not None
        else 300.0
    )
    labels = {
        "app.kubernetes.io/name": "switchyard",
        "app.kubernetes.io/instance": name,
        "scaled-evals.nvidia.com/evaluation-id": evaluation_id,
    }
    if benchmark_run_id is not None:
        labels["scaled-evals.nvidia.com/benchmark-run-id"] = benchmark_run_id
    routing_profiles_text = _routing_profiles_text(config)
    secret_env = _secret_env(config, credential_env)
    non_secret_env = _non_secret_env(config)
    azure_workload_identity = _wants_azure_workload_identity(non_secret_env)
    if azure_workload_identity:
        _validate_azure_workload_identity_env(non_secret_env)
        if config.env.get(_AZURE_ENTRA_TOKEN_ENV):
            raise ValueError(f"{_AZURE_ENTRA_TOKEN_ENV} is managed by scaled-evals and must not be set")
    service_account_name = config.service_account_name
    _validate_required_env_refs(
        routing_profiles_text,
        {**secret_env, **non_secret_env},
    )
    command = config.command or ["switchyard"]
    args = config.args or _default_switchyard_args(config)

    items = [
        _config_map(
            name=config_map_name,
            namespace=resolved_namespace,
            labels=labels,
            routing_profiles_text=routing_profiles_text,
        ),
        _secret(name=secret_name, namespace=resolved_namespace, labels=labels, values=secret_env),
        _deployment(
            name=name,
            namespace=resolved_namespace,
            labels=labels,
            image=resolved_image,
            image_pull_policy=config.image_pull_policy,
            image_pull_secrets=resolved_image_pull_secrets,
            service_account_name=service_account_name,
            command=command,
            args=args,
            port=config.port,
            config_map_name=config_map_name,
            secret_name=secret_name,
            secret_keys=sorted(secret_env),
            non_secret_env=non_secret_env,
            resources=config.resources,
            replicas=config.replicas,
            readiness_path=config.readiness_path,
            readiness_timeout_seconds=config.readiness_timeout_seconds,
            run_as_user=config.run_as_user or _DEFAULT_RUN_AS_USER,
        ),
        _service(name=service_name, namespace=resolved_namespace, labels=labels, port=config.port),
    ]
    if config.sandbox_egress_network_policy:
        items.append(
            _sandbox_egress_network_policy(
                name=network_policy_name,
                namespace=resolved_namespace,
                labels=labels,
                evaluation_id=evaluation_id,
                benchmark_run_id=benchmark_run_id,
                switchyard_labels=labels,
                port=config.port,
            )
        )
    apply_object = {"apiVersion": "v1", "kind": "List", "items": items}
    redacted_object = _redacted_apply_object(apply_object)
    lease = SwitchyardLease(
        mode="managed",
        profile_id=profile_id,
        benchmark_run_id=benchmark_run_id,
        namespace=resolved_namespace,
        name=name,
        service_name=service_name,
        config_map_name=config_map_name,
        secret_name=secret_name,
        network_policy_name=network_policy_name if config.sandbox_egress_network_policy else None,
        endpoint=endpoint,
        openai_base_url=openai_base_url,
        anthropic_base_url=anthropic_base_url,
        inbound=inbound,
        book_mode=config.book_mode,
        port=config.port,
        image_ref=resolved_image,
        image_digest=config.image_digest,
        source_project=config.source_project,
        source_ref=config.source_ref,
        source_commit=config.source_commit or config.source_ref,
        context_path=config.context_path,
        dockerfile_path=config.dockerfile_path,
        dockerfile_sha256=config.dockerfile_sha256,
        context_hash=config.context_hash,
        resource_labels=labels,
        manifest_hash=_value_hash(redacted_object),
        config_hash=_value_hash(_redacted_profile_config(config)),
        drain_seconds=resolved_drain,
        routing_stats_path=config.routing_stats_path,
        routing_stats_max_bytes=config.routing_stats_max_bytes,
        artifact_path=f"{SWITCHYARD_ARTIFACT_DIR}/",
    )
    return SwitchyardRender(
        lease=lease,
        apply_object=apply_object,
        redacted_object=redacted_object,
        routing_profiles_text=routing_profiles_text,
        runner_env=switchyard_runner_env(lease),
    )


def _render_external_switchyard(
    *,
    evaluation_id: str,
    profile_id: str,
    config: SwitchyardProfileConfig,
    credential_env: Mapping[str, str],
    external_allowed_hosts: tuple[str, ...],
) -> SwitchyardRender:
    endpoint = _validated_external_endpoint(
        config.endpoint or "",
        allowed_hosts=external_allowed_hosts,
    )
    client_token = credential_env.get("SWITCHYARD_API_KEY")
    if not client_token:
        raise ValueError("external switchyard profile requires an evaluation credential with provider 'switchyard'")
    inbound = config.switchyard_inbound or config.inbound
    endpoint_identity = _value_hash(
        {
            "scheme": "https",
            "authority": urlsplit(endpoint).netloc.lower(),
            "path": urlsplit(endpoint).path,
        }
    )
    warning = (
        "External Switchyard is operator-approved but not provisioned, health-checked, "
        "or log-captured by scaled-evals; its operator owns routing, retention, and trust."
    )
    lease = SwitchyardLease(
        profile_id=profile_id,
        mode="external",
        endpoint=endpoint,
        openai_base_url=f"{endpoint}/v1",
        anthropic_base_url=endpoint,
        inbound=inbound,
        book_mode=config.book_mode,
        port=urlsplit(endpoint).port or 443,
        endpoint_identity=endpoint_identity,
        config_hash=_value_hash(_redacted_profile_config(config)),
        drain_seconds=0,
        artifact_path=f"{SWITCHYARD_ARTIFACT_DIR}/",
        trust_warning=warning,
    )
    redacted_object = {
        "mode": "external",
        "managed_resources": [],
        "endpoint": endpoint,
        "endpoint_identity": endpoint_identity,
        "trust_warning": warning,
    }
    return SwitchyardRender(
        lease=lease,
        apply_object={"apiVersion": "v1", "kind": "List", "items": []},
        redacted_object=redacted_object,
        routing_profiles_text="{}",
        runner_env=switchyard_runner_env(lease, client_token=client_token),
    )


def _validated_external_endpoint(endpoint: str, *, allowed_hosts: tuple[str, ...]) -> str:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("external switchyard endpoint is not a valid URL") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("external switchyard endpoint must use https")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise ValueError("external switchyard endpoint must contain a hostname and no userinfo")
    if parsed.query or parsed.fragment:
        raise ValueError("external switchyard endpoint must not contain query or fragment data")
    host = parsed.hostname.lower().rstrip(".")
    if host in {"localhost", "metadata", "metadata.google.internal", "instance-data"}:
        raise ValueError("external switchyard endpoint hostname is prohibited")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if host.endswith((".localhost", ".local", ".internal")):
            raise ValueError("external switchyard endpoint must not use a local hostname") from None
        if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
            raise ValueError("external switchyard endpoint hostname is invalid") from None
    else:
        raise ValueError("external switchyard endpoint must use an approved DNS hostname")
    if "." not in host:
        raise ValueError("external switchyard endpoint must use a fully-qualified hostname")
    if not allowed_hosts:
        raise ValueError("external switchyard endpoints are disabled; configure SWITCHYARD_EXTERNAL_ALLOWED_HOSTS")
    if not any(_hostname_matches(host, pattern) for pattern in allowed_hosts):
        raise ValueError("external switchyard endpoint hostname is not operator-approved")
    authority = host if port in {None, 443} else f"{host}:{port}"
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        raise ValueError("external switchyard endpoint must be the service root, not /v1")
    return urlunsplit(("https", authority, path, "", ""))


def validate_switchyard_profile_config(
    raw_config: Mapping[str, Any],
    *,
    external_allowed_hosts: tuple[str, ...] | None = None,
) -> SwitchyardProfileConfig:
    """Validate profile shape and the operator-owned external trust boundary."""
    config = SwitchyardProfileConfig.model_validate(raw_config or {})
    if config.mode == "external":
        allowed_hosts = external_allowed_hosts
        if allowed_hosts is None:
            allowed_hosts = tuple(
                item.strip() for item in settings.switchyard_external_allowed_hosts.split(",") if item.strip()
            )
        _validated_external_endpoint(config.endpoint or "", allowed_hosts=allowed_hosts)
    return config


def _hostname_matches(host: str, pattern: str) -> bool:
    normalized = pattern.strip().lower().rstrip(".")
    if normalized.startswith("*."):
        suffix = normalized[1:]
        return host.endswith(suffix) and host != suffix[1:]
    return host == normalized


def switchyard_runner_env(
    lease: SwitchyardLease,
    *,
    client_token: str = "switchyard",
) -> dict[str, str]:
    """Env passed to runners so model traffic routes through Switchyard.

    Managed mode uses a placeholder because upstream keys live in its Secret.
    External mode supplies its evaluation-scoped client token. OpenAI/Codex/Gym
    use ``/v1``; Anthropic/Claude does not.
    """
    env: dict[str, str] = {}
    if lease.inbound in {"openai", "both"}:
        env.update(
            {
                "OPENAI_BASE_URL": lease.openai_base_url,
                "OPENAI_API_KEY": client_token,
                "NVIDIA_BASE_URL": lease.openai_base_url,
                "NVIDIA_API_KEY": client_token,
                "POLICY_BASE_URL": lease.openai_base_url,
                "POLICY_API_KEY": client_token,
                "NGC_INFERENCE_API_KEY": client_token,
            }
        )
    if lease.inbound in {"anthropic", "both"}:
        env.update(
            {
                "ANTHROPIC_BASE_URL": lease.anthropic_base_url,
                "ANTHROPIC_AUTH_TOKEN": client_token,
                "ANTHROPIC_API_KEY": client_token,
            }
        )
    return env


def switchyard_routing_headers(*, task: str, session_id: str) -> dict[str, str]:
    """Request metadata used by Switchyard routing logs and session statistics."""
    return {
        _ROUTING_TASK_HEADER: task,
        _ROUTING_SESSION_HEADER: session_id,
    }


def switchyard_routing_runner_env(*, task: str, session_id: str) -> dict[str, str]:
    """Render routing metadata for agents that call Switchyard.

    The task labels routing records, while the session groups token usage
    returned by ``/v1/routing/session-stats``. These headers do not configure
    or enable an Intake sink.
    """
    headers = switchyard_routing_headers(task=task, session_id=session_id)
    return {
        "SWITCHYARD_INTAKE_TASK": task,
        "SWITCHYARD_SESSION_ID": session_id,
        **inference_header_runner_env(headers),
    }


def write_switchyard_artifacts(render: SwitchyardRender, artifact_root: Path) -> None:
    root = _switchyard_artifact_root(artifact_root)
    root.mkdir(parents=True, exist_ok=True)
    (root / ROUTES_FILE_NAME).write_text(
        redact_secret_text(render.routing_profiles_text).rstrip() + "\n",
        encoding="utf-8",
    )
    (root / MANIFEST_FILE_NAME).write_text(
        json.dumps(render.redacted_object, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / LEASE_FILE_NAME).write_text(
        render.lease.model_dump_json(indent=2, exclude_none=True) + "\n",
        encoding="utf-8",
    )


def _run_kubectl(args: list[str], input_text: str | None) -> KubectlResult:
    return execute_kubectl(args, input_text, runner=subprocess.run)


def _switchyard_status_text(*, resources: KubectlResult, pods: KubectlResult) -> str:
    return json.dumps(
        {
            "resources": _kubectl_json_or_text(resources),
            "pods": _kubectl_json_or_text(pods),
        },
        indent=2,
        sort_keys=True,
    )


def _kubectl_json_or_text(result: KubectlResult) -> dict[str, Any]:
    payload = result.stdout or result.stderr
    try:
        data = json.loads(payload) if payload else None
    except json.JSONDecodeError:
        data = payload
    captured = {"returncode": result.returncode, "data": data}
    if result.stderr:
        captured["stderr"] = result.stderr
    return captured


def _switchyard_pod_restarts(result: KubectlResult) -> list[tuple[str, int]]:
    try:
        payload = json.loads(result.stdout) if result.stdout else {}
    except json.JSONDecodeError:
        return []
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    pods: list[tuple[str, int]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        status = item.get("status")
        if not isinstance(metadata, dict) or not isinstance(status, dict):
            continue
        name = metadata.get("name")
        if not isinstance(name, str) or not name:
            continue
        container_statuses = status.get("containerStatuses")
        restart_count = 0
        if isinstance(container_statuses, list):
            restart_count = sum(
                int(container.get("restartCount") or 0)
                for container in container_statuses
                if isinstance(container, dict) and container.get("name") == "switchyard"
            )
        pods.append((name, restart_count))
    return pods


def _default_switchyard_args(config: SwitchyardProfileConfig) -> list[str]:
    args = [
        "serve",
        "--routes",
        f"/etc/switchyard/{ROUTES_FILE_NAME}",
        "--host",
        "0.0.0.0",
        "--port",
        str(config.port),
        "--inbound",
        config.switchyard_inbound or config.inbound,
    ]
    args.extend(["--routing-log-file", ROUTING_LOG_FILE_PATH])
    return args


def _routing_profiles_text(config: SwitchyardProfileConfig) -> str:
    raw = (
        config.routing_profiles_yaml
        or config.routing_profiles_yml
        or config.switchyard_routing_profiles_yaml
        or config.switchyard_routing_profiles_yml
    )
    if raw is not None:
        loaded = yaml.safe_load(raw)
        if not isinstance(loaded, dict):
            raise ValueError("Switchyard routing profiles must be a YAML object")
        routing_profiles = loaded
    elif config.routing_profiles is not None:
        routing_profiles = config.routing_profiles
    else:
        routing_profiles = {
            "defaults": {
                "api_key": "${OPENAI_API_KEY}",
                "base_url": config.upstream_base_url,
                "format": "openai",
            },
            "routes": {
                "switchyard": {
                    "type": "passthrough",
                }
            },
        }
    return yaml.safe_dump(_with_default_inference_priority(routing_profiles), sort_keys=False)


def _with_default_inference_priority(value: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the batch default to configurable Switchyard target headers."""

    def visit(item: Any) -> Any:
        if isinstance(item, Mapping):
            rendered = {str(key): visit(child) for key, child in item.items()}
            if "extra_headers" in rendered:
                headers = rendered["extra_headers"]
                if not isinstance(headers, Mapping):
                    raise ValueError("Switchyard extra_headers must be an object")
                rendered["extra_headers"] = with_default_inference_priority(headers)
            return rendered
        if isinstance(item, list):
            return [visit(child) for child in item]
        return item

    rendered = visit(value)
    defaults = rendered.setdefault("defaults", {})
    if not isinstance(defaults, dict):
        raise ValueError("Switchyard routing profile defaults must be an object")
    headers = defaults.get("extra_headers", {})
    if not isinstance(headers, Mapping):
        raise ValueError("Switchyard defaults.extra_headers must be an object")
    defaults["extra_headers"] = with_default_inference_priority(headers)
    return rendered


def _config_map(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    routing_profiles_text: str,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": namespace, "labels": dict(labels)},
        "data": {ROUTES_FILE_NAME: routing_profiles_text},
    }


def _secret(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    values: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name, "namespace": namespace, "labels": dict(labels)},
        "type": "Opaque",
        "stringData": dict(values),
    }


def _deployment(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    image: str,
    image_pull_policy: str,
    image_pull_secrets: list[str],
    service_account_name: str | None,
    command: list[str],
    args: list[str],
    port: int,
    config_map_name: str,
    secret_name: str,
    secret_keys: list[str],
    non_secret_env: Mapping[str, str],
    resources: Mapping[str, Any],
    replicas: int,
    readiness_path: str,
    readiness_timeout_seconds: int,
    run_as_user: int,
) -> dict[str, Any]:
    pod_spec: dict[str, Any] = {
        "securityContext": {
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": "switchyard",
                "image": image,
                "imagePullPolicy": image_pull_policy,
                "command": command,
                "args": args,
                "env": [
                    {
                        "name": key,
                        "valueFrom": {
                            "secretKeyRef": {
                                "name": secret_name,
                                "key": key,
                                "optional": True,
                            }
                        },
                    }
                    for key in secret_keys
                ]
                + [{"name": key, "value": value} for key, value in sorted(non_secret_env.items())],
                "ports": [{"name": "http", "containerPort": port}],
                "readinessProbe": {
                    "httpGet": {"path": readiness_path, "port": "http"},
                    "initialDelaySeconds": 5,
                    "periodSeconds": 10,
                },
                "livenessProbe": {
                    "httpGet": {"path": readiness_path, "port": "http"},
                    "initialDelaySeconds": 15,
                    "periodSeconds": 30,
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                    "runAsNonRoot": True,
                    "runAsUser": run_as_user,
                    "seccompProfile": {"type": "RuntimeDefault"},
                },
                "resources": dict(resources),
                "volumeMounts": [
                    {
                        "name": "routes",
                        "mountPath": "/etc/switchyard",
                        "readOnly": True,
                    },
                    {
                        "name": "routing-log",
                        "mountPath": "/var/lib/switchyard",
                    },
                ],
            }
        ],
        "volumes": [
            {"name": "routes", "configMap": {"name": config_map_name}},
            {"name": "routing-log", "emptyDir": {}},
        ],
    }
    if image_pull_secrets:
        pod_spec["imagePullSecrets"] = [{"name": item} for item in image_pull_secrets]
    if service_account_name:
        pod_spec["serviceAccountName"] = service_account_name
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace, "labels": dict(labels)},
        "spec": {
            "replicas": replicas,
            "progressDeadlineSeconds": readiness_timeout_seconds,
            "selector": {"matchLabels": dict(labels)},
            "template": {
                "metadata": {
                    "labels": dict(labels),
                    "annotations": {"cluster-autoscaler.kubernetes.io/safe-to-evict": "false"},
                },
                "spec": pod_spec,
            },
        },
    }


def _service(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    port: int,
) -> dict[str, Any]:
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name, "namespace": namespace, "labels": dict(labels)},
        "spec": {
            "type": "ClusterIP",
            "selector": dict(labels),
            "ports": [{"name": "http", "port": port, "targetPort": "http"}],
        },
    }


def _sandbox_egress_network_policy(
    *,
    name: str,
    namespace: str,
    labels: Mapping[str, str],
    evaluation_id: str,
    benchmark_run_id: str | None,
    switchyard_labels: Mapping[str, str],
    port: int,
) -> dict[str, Any]:
    """Allow sandbox-k8s pods to reach this eval's Switchyard service port."""
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": namespace, "labels": dict(labels)},
        "spec": {
            "podSelector": {
                "matchLabels": {
                    "app.kubernetes.io/managed-by": "sandbox-k8s",
                    (
                        "scaled-evals.nvidia.com/benchmark-run-id"
                        if benchmark_run_id is not None
                        else "scaled-evals.nvidia.com/evaluation-id"
                    ): benchmark_run_id or evaluation_id,
                },
            },
            "policyTypes": ["Egress"],
            "egress": [
                {
                    # The injected endpoint is a cluster Service DNS name. Keep
                    # name resolution available while all non-DNS destinations
                    # remain governed by the direct-egress policy.
                    "to": [
                        {
                            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}},
                            "podSelector": {"matchLabels": {"k8s-app": "kube-dns"}},
                        },
                        {
                            "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "openshift-dns"}},
                            "podSelector": {"matchLabels": {"dns.operator.openshift.io/daemonset-dns": "default"}},
                        },
                    ],
                    "ports": [
                        {"protocol": "UDP", "port": 53},
                        {"protocol": "TCP", "port": 53},
                    ],
                },
                {
                    "to": [{"podSelector": {"matchLabels": dict(switchyard_labels)}}],
                    "ports": [{"protocol": "TCP", "port": port}],
                },
            ],
        },
    }


def _secret_env(
    config: SwitchyardProfileConfig,
    credential_env: Mapping[str, str],
) -> dict[str, str]:
    # Values in credential_env have already been decrypted from an explicitly
    # selected credential. Binding targets are intentionally arbitrary valid
    # environment names, so do not infer secrecy from their spelling.
    env = dict(credential_env)
    for key, value in config.env.items():
        if _is_secret_env_key(key):
            env[key] = value
    if env.get("OPENAI_API_KEY") and not env.get("NVIDIA_API_KEY"):
        env["NVIDIA_API_KEY"] = env["OPENAI_API_KEY"]
    if env.get("NVIDIA_API_KEY") and not env.get("OPENAI_API_KEY"):
        env["OPENAI_API_KEY"] = env["NVIDIA_API_KEY"]
    if env.get("NGC_INFERENCE_API_KEY") and not env.get("NVIDIA_API_KEY"):
        env["NVIDIA_API_KEY"] = env["NGC_INFERENCE_API_KEY"]
    if env.get("POLICY_API_KEY") and not env.get("OPENAI_API_KEY"):
        env["OPENAI_API_KEY"] = env["POLICY_API_KEY"]
    for key in _DEFAULT_SECRET_KEYS:
        env.setdefault(key, "")
    return {key: str(value) for key, value in env.items()}


def _non_secret_env(config: SwitchyardProfileConfig) -> dict[str, str]:
    env = {key: value for key, value in config.env.items() if not _is_secret_env_key(key)}
    env.setdefault("OPENAI_BASE_URL", config.upstream_base_url)
    env.setdefault("NVIDIA_BASE_URL", config.upstream_base_url)
    return {key: str(value) for key, value in env.items()}


def _wants_azure_workload_identity(env: Mapping[str, str]) -> bool:
    return bool(env.get(_AZURE_CLIENT_ID_ENV, "").strip())


def _validate_azure_workload_identity_env(env: Mapping[str, str]) -> None:
    if not env.get(_AZURE_TENANT_ID_ENV, "").strip():
        raise ValueError(f"switchyard profile sets {_AZURE_CLIENT_ID_ENV} but {_AZURE_TENANT_ID_ENV} is empty")


def _mint_azure_entra_token(env: Mapping[str, str]) -> str:
    """Mint an Azure bearer from the dispatch worker's projected identity."""
    _validate_azure_workload_identity_env(env)
    assertion = Path(os.environ.get(_AZURE_FEDERATED_TOKEN_FILE_ENV, _AZURE_FEDERATED_TOKEN_PATH)).read_text()
    tenant_id = env[_AZURE_TENANT_ID_ENV].strip()
    error: Exception | None = None
    for attempt in range(3):
        try:
            response = httpx.post(
                f"{_DEFAULT_AZURE_AUTHORITY_HOST}{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": env[_AZURE_CLIENT_ID_ENV].strip(),
                    "scope": _AZURE_TOKEN_SCOPE,
                    "client_assertion_type": ("urn:ietf:params:oauth:client-assertion-type:jwt-bearer"),
                    "client_assertion": assertion,
                },
                timeout=30,
            )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not token:
                raise ValueError("Azure token response has no access_token")
            return str(token)
        except (httpx.HTTPError, ValueError) as exc:
            error = exc
            if attempt < 2:
                time.sleep(2)
    raise RuntimeError("Azure token exchange failed after 3 attempts") from error


def _validate_required_env_refs(
    routing_profiles_text: str,
    env: Mapping[str, str],
) -> None:
    required = {match.group(1) for match in _ENV_REF_RE.finditer(routing_profiles_text) if not match.group(2)}
    missing = sorted(name for name in required if not env.get(name))
    if missing:
        raise ValueError("switchyard route profile references missing credential env var(s): " + ", ".join(missing))


def _redacted_apply_object(apply_object: Mapping[str, Any]) -> dict[str, Any]:
    return _redacted_value(apply_object)


def _redacted_profile_config(config: SwitchyardProfileConfig) -> dict[str, Any]:
    return _redacted_value(config.model_dump(exclude_none=True))


def _redacted_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text == "stringData" or _is_secret_env_key(key_text):
                if isinstance(item, Mapping):
                    redacted[key_text] = {str(child): "<redacted>" for child in item}
                else:
                    redacted[key_text] = "<redacted>"
            else:
                redacted[key_text] = _redacted_value(item)
        return redacted
    if isinstance(value, list):
        return [_redacted_value(item) for item in value]
    if isinstance(value, str):
        return redact_secret_text(value)
    return value


def _resource_name(prefix: str, evaluation_id: str) -> str:
    raw = _dns_label(f"{prefix}-{evaluation_id}", max_length=48)
    digest = hashlib.sha256(evaluation_id.encode("utf-8")).hexdigest()[:10]
    return _dns_label(f"{raw}-{digest}", max_length=63)


def _dns_label(value: str, *, max_length: int) -> str:
    text = _DNS_RE.sub("-", value.lower()).strip("-")
    text = re.sub("-+", "-", text)
    if not text:
        text = "switchyard"
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text


def _switchyard_artifact_root(artifact_root: Path) -> Path:
    return artifact_root / SWITCHYARD_ARTIFACT_DIR


def _label_selector(lease: SwitchyardLease) -> str:
    return ",".join(f"{key}={value}" for key, value in sorted(lease.resource_labels.items()))


def _switchyard_get_resource_refs(lease: SwitchyardLease) -> list[str]:
    refs = [
        f"deployment/{lease.name}",
        f"service/{lease.service_name}",
    ]
    if lease.network_policy_name:
        refs.append(f"networkpolicy/{lease.network_policy_name}")
    return refs


def _is_secret_env_key(key: str) -> bool:
    return bool(_SECRET_ENV_RE.search(key))


def _value_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
