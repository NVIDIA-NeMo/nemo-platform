# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Evaluator plugin container-backed metric bundle implementation."""

from __future__ import annotations

import asyncio
import atexit
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Any, Literal, Protocol, runtime_checkable
from urllib.parse import urljoin

import cloudpickle
import httpx
import nemo_evaluator.shared.metric_bundles.metric_server as metric_server_package
from nemo_evaluator.shared.metric_bundles.bundles import (
    BundledMetricOutputSpec,
    BundleMetricTypeName,
    MetricBundle,
    MetricBundlePayload,
    MetricBundler,
    MetricBundlingError,
    metric_metadata,
    metric_secrets,
    register_metric_bundle_payload,
    register_metric_bundler,
    validate_metric_type,
)
from nemo_evaluator.shared.metric_bundles.container_image import default_metric_server_image
from nemo_evaluator_sdk.metrics.protocol import Metric, MetricInput, MetricOutputSpec, MetricResult
from nemo_evaluator_sdk.values.common import SecretRef
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, RootModel, StringConstraints

NonEmptyString = Annotated[str, StringConstraints(min_length=1)]
_METRIC_ARTIFACT_NAME = "metric.pkl"
_SERVER_PACKAGE_NAME = "nemo_metric_server"
_SCORE_PATH = "/score"
_HEALTH_PATH = "/health"
_TIMEOUT_SECONDS = 30.0
_SERVER_HOST = "0.0.0.0"
_SERVER_PORT = 8000
_KEEP_CONTAINERS_ENV_VAR = "NEMO_EVALUATOR_KEEP_METRIC_CONTAINERS"
_METRIC_DESCRIPTOR_NAME = "descriptor.json"
_DOCKER_PORT_TIMEOUT_SECONDS = 5.0
_IMAGE_NAME_METRIC_TYPE_MAX_LENGTH = 80


class MetricContainerBuildSpec(BaseModel):
    """Metric-owned Python dependencies needed by the generated metric image."""

    model_config = ConfigDict(extra="forbid")

    requirements: list[str] = Field(default_factory=list)


@runtime_checkable
class MetricWithContainerBuild(Protocol):
    """Protocol for metrics that declare their container build metadata."""

    def container_build_spec(self) -> object:
        """Return the metric-specific build metadata used for container bundling."""
        ...


class ContainerImageBuilder(Protocol):
    """Builds a container image from a generated metric server context."""

    def build(self, *, context_dir: Path, image: str) -> None:
        """Build a container image from ``context_dir`` and tag it as ``image``."""
        ...


class RunningMetricContainer(Protocol):
    """A launched metric service container."""

    endpoint_url: NonEmptyString

    def diagnostics(self) -> str:
        """Return human-readable container diagnostics."""
        ...

    def stop(self) -> None:
        """Stop the metric service container."""
        ...


class MetricContainerLauncher(Protocol):
    """Launches generated metric service images."""

    def launch(self, *, image: str) -> RunningMetricContainer:
        """Start ``image`` and return its reachable endpoint."""
        ...


class DockerCLIContainerImageBuilder:
    """Container image builder that shells out to Docker."""

    def build(self, *, context_dir: Path, image: str) -> None:
        """Run ``docker build`` for the generated metric server image."""
        subprocess.run(["docker", "build", "-t", image, str(context_dir)], check=True)


@dataclass
class _DockerRunningMetricContainer:
    """Running Docker metric service container with process-exit cleanup."""

    container_id: str
    endpoint_url: NonEmptyString
    docker_executable: str = "docker"
    keep_alive: bool = False

    _stopped: bool = False

    def __post_init__(self) -> None:
        if not self.keep_alive:
            atexit.register(self.stop)

    def stop(self) -> None:
        """Stop the Docker container if it is still running."""
        if self._stopped or self.keep_alive:
            return
        self._stopped = True
        subprocess.run(
            [self.docker_executable, "stop", self.container_id],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def diagnostics(self) -> str:
        """Return Docker logs for readiness and scoring diagnostics."""
        logs = subprocess.run(
            [self.docker_executable, "logs", "--tail", "100", self.container_id],
            check=False,
            capture_output=True,
            text=True,
        )
        return "\n".join(
            part
            for part in (
                f"container_id={self.container_id}",
                logs.stdout.strip(),
                logs.stderr.strip(),
            )
            if part
        )


class DockerCLIMetricContainerLauncher:
    """Metric container launcher that shells out to Docker."""

    def __init__(self, *, docker_executable: str = "docker", keep_alive: bool | None = None) -> None:
        self._docker_executable = docker_executable
        self._keep_alive = _keep_alive_from_env() if keep_alive is None else keep_alive

    def launch(self, *, image: str) -> RunningMetricContainer:
        """Run a generated metric service image and return its local endpoint."""
        command = [
            self._docker_executable,
            "run",
            "-d",
            "-p",
            f"127.0.0.1::{_SERVER_PORT}",
        ]
        if not self._keep_alive:
            command.append("--rm")
        command.append(image)
        container_id = self._run(command).strip()
        try:
            port_mapping = self._port_mapping(container_id)
            return _DockerRunningMetricContainer(
                container_id=container_id,
                endpoint_url=f"http://{port_mapping}",
                docker_executable=self._docker_executable,
                keep_alive=self._keep_alive,
            )
        except Exception:
            subprocess.run(
                [self._docker_executable, "stop", container_id],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            raise

    @staticmethod
    def _run(command: list[str]) -> str:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return result.stdout

    def _port_mapping(self, container_id: str) -> str:
        deadline = time.monotonic() + _DOCKER_PORT_TIMEOUT_SECONDS
        command = [self._docker_executable, "port", container_id, f"{_SERVER_PORT}/tcp"]
        last_error: subprocess.CalledProcessError | None = None
        while time.monotonic() < deadline:
            try:
                port_mapping = self._run(command).strip()
                if port_mapping:
                    return port_mapping
            except subprocess.CalledProcessError as exc:
                last_error = exc
            time.sleep(0.1)
        raise MetricBundlingError(
            f"container port {_SERVER_PORT}/tcp was not published for {container_id}"
        ) from last_error


def _keep_alive_from_env() -> bool:
    return os.environ.get(_KEEP_CONTAINERS_ENV_VAR, "").lower() in {"1", "true", "yes", "on"}


class ContainerMetricPayload(MetricBundlePayload):
    """HTTP container payload for a generated metric service image."""

    model_config = ConfigDict(extra="ignore")

    image: NonEmptyString

    @property
    def kind(self) -> Literal["container-http"]:
        """Payload discriminator used by the metric bundle registry."""
        return "container-http"


class ContainerMetricBundler(MetricBundler):
    """Bundler that builds a metric-specific HTTP container image."""

    def __init__(
        self,
        *,
        builder: ContainerImageBuilder | None = None,
        launcher: MetricContainerLauncher | None = None,
    ) -> None:
        self._builder = builder or DockerCLIContainerImageBuilder()
        self._launcher = launcher or DockerCLIMetricContainerLauncher()

    def bundle(self, metric: Metric) -> MetricBundle:
        """Build a metric server image and return its executable bundle entity."""
        metric_type = validate_metric_type(metric)
        build_spec = _metric_container_build_spec(metric)
        metric_blob = cloudpickle.dumps(metric)
        outputs = [BundledMetricOutputSpec.from_output_spec(output) for output in metric.output_spec()]
        secrets = metric_secrets(metric)
        image = _default_image_name(metric_type=metric_type, build_spec=build_spec, blob=metric_blob)
        payload = ContainerMetricPayload(image=image)

        with TemporaryDirectory(prefix="nemo-evaluator-container-metric-") as temp_dir:
            context_dir = Path(temp_dir)
            _write_build_context(
                context_dir=context_dir,
                build_spec=build_spec,
                descriptor=_metric_descriptor(metric_type=metric_type, outputs=outputs),
                metric_blob=metric_blob,
            )
            self._builder.build(context_dir=context_dir, image=image)

        return MetricBundle(
            metric_type=metric_type,
            metadata=metric_metadata(metric),
            outputs=outputs,
            secrets=secrets,
            payload=payload,
            digest=_container_metric_digest(
                metric_type=metric_type,
                payload=payload,
                outputs=outputs,
                secrets=secrets,
            ),
        )

    def unbundle(self, metric: MetricBundle) -> Metric:
        """Hydrate a runtime metric proxy for a container metric bundle."""
        payload = _container_payload(metric.payload)
        _verify_container_metric_digest(metric, payload)
        container = self._launcher.launch(image=payload.image)
        try:
            return _container_metric_client(metric, endpoint_url=container.endpoint_url, container=container)
        except Exception:
            container.stop()
            raise


def hydrate_container_metric(
    metric: MetricBundle,
    *,
    endpoint_url: NonEmptyString | None = None,
    container: RunningMetricContainer | None = None,
) -> Metric:
    """Hydrate a runtime metric proxy for a launched container metric bundle."""
    payload = _container_payload(metric.payload)
    _verify_container_metric_digest(metric, payload)
    effective_endpoint_url = container.endpoint_url if container is not None else endpoint_url
    if effective_endpoint_url is None:
        raise MetricBundlingError("container metric bundles require a runtime endpoint before hydration")
    return _container_metric_client(metric, endpoint_url=effective_endpoint_url, container=container)


def _verify_container_metric_digest(metric: MetricBundle, payload: ContainerMetricPayload) -> None:
    expected_digest = _container_metric_digest(
        metric_type=metric.metric_type,
        payload=payload,
        outputs=metric.outputs,
        secrets=metric.secrets,
    )
    if expected_digest != metric.digest:
        raise MetricBundlingError("metric bundle digest does not match payload")


def _container_metric_client(
    metric: MetricBundle,
    *,
    endpoint_url: NonEmptyString,
    container: RunningMetricContainer | None = None,
) -> Metric:
    return _ContainerMetricClient(
        type=metric.metric_type,
        outputs=metric.outputs,
        endpoint_url=endpoint_url,
        container=container,
        secret_refs=metric.secrets,
        description=metric.metadata.description,
        labels=metric.metadata.labels,
    )


def _container_payload(payload: MetricBundlePayload) -> ContainerMetricPayload:
    if isinstance(payload, ContainerMetricPayload):
        return payload
    return ContainerMetricPayload.model_validate(payload.model_dump(mode="python"))


class _BundleOutputValue(RootModel[Any]):
    """Permissive output value used when a container bundle only carries JSON schema metadata."""


def _to_output_spec(output: BundledMetricOutputSpec) -> MetricOutputSpec:
    if output.value_kind == "continuous":
        return MetricOutputSpec.continuous_score(output.name, description=output.description)
    if output.value_kind == "discrete":
        return MetricOutputSpec.discrete_score(output.name, description=output.description)
    if output.value_kind == "label":
        return MetricOutputSpec.label(output.name, description=output.description)
    if output.value_kind == "boolean":
        return MetricOutputSpec.boolean(output.name, description=output.description)
    return MetricOutputSpec.model(output.name, _BundleOutputValue, description=output.description)


class _ContainerMetricClient(BaseModel):
    """Runtime metric proxy for a long-lived HTTP metric container."""

    model_config = ConfigDict(extra="forbid")

    type: BundleMetricTypeName
    outputs: list[BundledMetricOutputSpec] = Field(min_length=1)
    endpoint_url: NonEmptyString
    secret_refs: dict[str, SecretRef] = Field(default_factory=dict)
    description: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)

    _client: httpx.AsyncClient | None = PrivateAttr(default=None)
    _container: RunningMetricContainer | None = PrivateAttr(default=None)

    def __init__(self, *, container: RunningMetricContainer | None = None, **data: object) -> None:
        super().__init__(**data)
        self._container = container

    def __deepcopy__(self, memo: dict[int, object] | None = None) -> _ContainerMetricClient:
        del memo
        return _ContainerMetricClient(
            type=self.type,
            outputs=self.outputs,
            endpoint_url=self.endpoint_url,
            secret_refs=self.secret_refs,
            description=self.description,
            labels=self.labels,
            container=self._container,
        )

    def __del__(self) -> None:
        container = getattr(self, "_container", None)
        if container is not None:
            container.stop()

    def output_spec(self) -> list[MetricOutputSpec]:
        """Return declared row-level outputs emitted by this metric service."""
        return [_to_output_spec(output) for output in self.outputs]

    def secrets(self) -> dict[str, SecretRef]:
        """Return secret env mappings required by this metric service."""
        return self.secret_refs

    async def preflight(self) -> None:
        """Verify that the external metric service is reachable."""
        await self._wait_until_ready()

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        """Compute structured score output through the container metric service."""
        async with self._client_context() as client:
            response = await client.post(
                _join_url(self.endpoint_url, _SCORE_PATH),
                json=input.model_dump(mode="json"),
            )
        response.raise_for_status()
        return MetricResult.model_validate(response.json())

    async def _wait_until_ready(self) -> None:
        health_url = _join_url(self.endpoint_url, _HEALTH_PATH)
        deadline = asyncio.get_running_loop().time() + _TIMEOUT_SECONDS
        last_error: Exception | None = None
        async with self._client_context() as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    response = await client.get(health_url)
                    response.raise_for_status()
                    return
                except Exception as exc:
                    last_error = exc
                    await asyncio.sleep(0.1)
        message = f"container metric service did not become ready at {health_url}"
        if self._container is not None:
            diagnostics = self._container.diagnostics()
            if diagnostics:
                message = f"{message}\n{diagnostics}"
        raise MetricBundlingError(message) from last_error

    @asynccontextmanager
    async def _client_context(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            yield client


def _write_build_context(
    *,
    context_dir: Path,
    build_spec: MetricContainerBuildSpec,
    descriptor: dict[str, object],
    metric_blob: bytes,
) -> None:
    (context_dir / _METRIC_ARTIFACT_NAME).write_bytes(metric_blob)
    (context_dir / _METRIC_DESCRIPTOR_NAME).write_text(json.dumps(descriptor, sort_keys=True), encoding="utf-8")
    shutil.copytree(
        Path(metric_server_package.__path__[0]),
        context_dir / _SERVER_PACKAGE_NAME,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    _write_requirements(context_dir / "requirements.txt", build_spec.requirements)
    (context_dir / "Dockerfile").write_text(_dockerfile(), encoding="utf-8")


def _write_requirements(path: Path, requirements: list[str]) -> None:
    path.write_text("\n".join(requirements) + "\n", encoding="utf-8")


def _dockerfile() -> str:
    template = files("nemo_evaluator.shared.metric_bundles").joinpath("templates", "Dockerfile.metric-container")
    return (
        template.read_text(encoding="utf-8")
        .replace("${BASE_IMAGE}", default_metric_server_image())
        .replace("${SERVER_PACKAGE_NAME}", _SERVER_PACKAGE_NAME)
        .replace("${METRIC_ARTIFACT_NAME}", _METRIC_ARTIFACT_NAME)
        .replace("${METRIC_DESCRIPTOR_NAME}", _METRIC_DESCRIPTOR_NAME)
        .replace("${SERVER_PORT}", str(_SERVER_PORT))
        .replace("${SERVER_COMMAND_JSON}", json.dumps(_server_command()))
    )


def _server_command() -> list[str]:
    return [
        "python",
        "-m",
        "nemo_metric_server",
        "--host",
        _SERVER_HOST,
        "--port",
        str(_SERVER_PORT),
    ]


def _metric_container_build_spec(metric: Metric) -> MetricContainerBuildSpec:
    if not isinstance(metric, MetricWithContainerBuild):
        return MetricContainerBuildSpec()
    value = metric.container_build_spec()
    if isinstance(value, MetricContainerBuildSpec):
        return value
    if isinstance(value, Mapping):
        return MetricContainerBuildSpec.model_validate(value)
    raise MetricBundlingError("metric container_build_spec() must return MetricContainerBuildSpec or a mapping")


def _metric_descriptor(*, metric_type: str, outputs: list[BundledMetricOutputSpec]) -> dict[str, object]:
    return {
        "type": metric_type,
        "input": {"schema": MetricInput.model_json_schema()},
        "outputs": [output.model_dump(mode="json") for output in outputs],
    }


def _default_image_name(*, metric_type: str, build_spec: MetricContainerBuildSpec, blob: bytes) -> str:
    encoded = json.dumps(build_spec.model_dump(mode="json"), sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(blob + encoded).hexdigest()[:12]
    safe_metric_type = _safe_image_component(metric_type)
    collision_suffix = hashlib.sha256(metric_type.encode("utf-8")).hexdigest()[:8]
    return f"nemo-evaluator-metric-{safe_metric_type}-{collision_suffix}:{digest}"


def _safe_image_component(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("._-")
    normalized = re.sub(r"[-_.]{2,}", "-", normalized)
    if not normalized:
        return "metric"
    return normalized[:_IMAGE_NAME_METRIC_TYPE_MAX_LENGTH].strip("._-") or "metric"


def _container_metric_digest(
    *,
    metric_type: str,
    payload: MetricBundlePayload,
    outputs: list[BundledMetricOutputSpec],
    secrets: dict[str, SecretRef],
) -> str:
    digest_payload = {
        "metric_type": metric_type,
        "payload": payload.model_dump(mode="json"),
        "outputs": [output.model_dump(mode="json") for output in outputs],
        "secrets": {key: value.model_dump(mode="json") for key, value in sorted(secrets.items())},
    }
    encoded = json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _join_url(base_url: str, path: str) -> str:
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


register_metric_bundle_payload("container-http", ContainerMetricPayload)
register_metric_bundler("container-http", ContainerMetricBundler)
