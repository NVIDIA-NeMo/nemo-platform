# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for container-backed metric bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol, cast

import httpx
import pytest
from nemo_evaluator.shared.metric_bundles import container as container_module
from nemo_evaluator.shared.metric_bundles.bundles import MetricBundle, MetricBundlingError
from nemo_evaluator.shared.metric_bundles.container import (
    ContainerImageBuilder,
    ContainerMetricBundler,
    ContainerMetricPayload,
    MetricContainerLauncher,
    RunningMetricContainer,
    hydrate_container_metric,
)
from nemo_evaluator.shared.metric_bundles.container_image import default_metric_server_image
from nemo_evaluator_sdk.metrics.protocol import (
    CandidateOutput,
    ContinuousScore,
    DatasetRow,
    MetricInput,
    MetricOutput,
    MetricOutputSpec,
    MetricResult,
)


def _default_base_image() -> str:
    return default_metric_server_image()


class _HydratedContainerMetric(Protocol):
    _client: httpx.AsyncClient | None

    def output_spec(self) -> list[MetricOutputSpec]: ...

    async def preflight(self) -> None: ...

    async def compute_scores(self, input: MetricInput) -> MetricResult: ...


class _RecordingImageBuilder(ContainerImageBuilder):
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []
        self.files: dict[str, str | bytes] = {}

    def build(self, *, context_dir: Path, image: str) -> None:
        self.calls.append((context_dir, image))
        self.files["Dockerfile"] = (context_dir / "Dockerfile").read_text(encoding="utf-8")
        self.files["requirements.txt"] = (context_dir / "requirements.txt").read_text(encoding="utf-8")
        self.files["descriptor.json"] = (context_dir / "descriptor.json").read_text(encoding="utf-8")
        self.files["nemo_metric_server/__main__.py"] = (context_dir / "nemo_metric_server" / "__main__.py").read_text(
            encoding="utf-8"
        )
        self.files["metric.pkl"] = (context_dir / "metric.pkl").read_bytes()


class _RunningMetricContainer:
    def __init__(self, endpoint_url: str) -> None:
        self.endpoint_url = endpoint_url
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True

    def diagnostics(self) -> str:
        return "fake container logs"


class _RecordingContainerLauncher(MetricContainerLauncher):
    def __init__(self, endpoint_url: str = "http://metric.test") -> None:
        self.endpoint_url = endpoint_url
        self.launched_images: list[str] = []
        self.containers: list[_RunningMetricContainer] = []

    def launch(self, *, image: str) -> RunningMetricContainer:
        self.launched_images.append(image)
        container = _RunningMetricContainer(self.endpoint_url)
        self.containers.append(container)
        return container


class _BuildableMetric:
    description = "Container metric"
    labels = {"runtime": "container"}

    @property
    def type(self) -> str:
        return "container-exact-match"

    def output_spec(self) -> list[MetricOutputSpec]:
        return [MetricOutputSpec.continuous_score("score")]

    async def compute_scores(self, input: MetricInput) -> MetricResult:
        expected = input.row.data.get("expected")
        score = 1.0 if input.candidate.output_text == expected else 0.0
        return MetricResult(outputs=[MetricOutput(name="score", value=score)])

    def container_build_spec(self) -> dict[str, list[str]]:
        return {"requirements": ["example-metric-dep==1.2.3"]}


def _bundle(builder: _RecordingImageBuilder | None = None) -> MetricBundle:
    return ContainerMetricBundler(builder=builder or _RecordingImageBuilder()).bundle(_BuildableMetric())


def test_container_metric_bundler_builds_image_context_and_returns_bundle() -> None:
    builder = _RecordingImageBuilder()

    bundle = _bundle(builder)

    assert builder.calls[0][1].startswith("nemo-evaluator-metric-container-exact-match-")
    assert f"FROM {_default_base_image()}" in str(builder.files["Dockerfile"])
    assert "example-metric-dep==1.2.3" in str(builder.files["requirements.txt"])
    assert "cloudpickle" not in str(builder.files["requirements.txt"])
    assert "COPY wheels/" not in str(builder.files["Dockerfile"])
    assert "COPY packages/" not in str(builder.files["Dockerfile"])
    assert 'CMD ["python", "-m", "nemo_metric_server"' in str(builder.files["Dockerfile"])
    assert "ThreadingHTTPServer" in str(builder.files["nemo_metric_server/__main__.py"])
    descriptor = json.loads(cast(str, builder.files["descriptor.json"]))
    assert descriptor["type"] == "container-exact-match"
    assert "input" in descriptor
    assert descriptor["outputs"][0]["name"] == "score"
    assert isinstance(builder.files["metric.pkl"], bytes)
    assert isinstance(bundle.payload, ContainerMetricPayload)
    assert bundle.metric_type == "container-exact-match"
    assert bundle.metadata.description == "Container metric"
    assert bundle.metadata.labels == {"runtime": "container"}
    assert bundle.outputs[0].name == "score"
    assert bundle.outputs[0].value_kind == "continuous"
    assert bundle.payload.image.startswith("nemo-evaluator-metric-container-exact-match-")
    assert "endpoint_url" not in bundle.model_dump(mode="json")["payload"]


def test_container_metric_bundler_uses_default_build_spec_without_metric_metadata() -> None:
    class _MetricWithoutBuildSpec:
        @property
        def type(self) -> str:
            return "no-build-spec"

        def output_spec(self) -> list[MetricOutputSpec]:
            return [MetricOutputSpec.continuous_score("score")]

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])

    builder = _RecordingImageBuilder()

    bundle = ContainerMetricBundler(builder=builder).bundle(_MetricWithoutBuildSpec())

    assert builder.calls[0][1].startswith("nemo-evaluator-metric-no-build-spec-")
    assert f"FROM {_default_base_image()}" in str(builder.files["Dockerfile"])
    assert str(builder.files["requirements.txt"]) == "\n"
    assert isinstance(bundle.payload, ContainerMetricPayload)
    assert bundle.payload.image.startswith("nemo-evaluator-metric-no-build-spec-")


def test_container_metric_bundler_normalizes_image_names_and_avoids_collisions() -> None:
    class _MetricWithAwkwardType:
        @property
        def type(self) -> str:
            return "Container/Metric:With Uppercase And Weird Chars!!!"

        def output_spec(self) -> list[MetricOutputSpec]:
            return [MetricOutputSpec.continuous_score("score")]

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])

    builder = _RecordingImageBuilder()

    bundle = ContainerMetricBundler(builder=builder).bundle(_MetricWithAwkwardType())
    payload = cast(ContainerMetricPayload, bundle.payload)

    assert payload.image.startswith("nemo-evaluator-metric-container-metric-with-uppercase-and-weird-chars-")
    assert payload.image == payload.image.lower()
    assert ":" in payload.image


def test_container_metric_bundler_rejects_invalid_build_spec() -> None:
    class _MetricWithInvalidBuildSpec:
        @property
        def type(self) -> str:
            return "invalid-build-spec"

        def output_spec(self) -> list[MetricOutputSpec]:
            return [MetricOutputSpec.continuous_score("score")]

        async def compute_scores(self, input: MetricInput) -> MetricResult:
            return MetricResult(outputs=[MetricOutput(name="score", value=1.0)])

        def container_build_spec(self) -> object:
            return ["not", "a", "mapping"]

    with pytest.raises(MetricBundlingError, match="container_build_spec"):
        ContainerMetricBundler(builder=_RecordingImageBuilder()).bundle(_MetricWithInvalidBuildSpec())


def test_container_metric_bundle_rejects_digest_mismatch() -> None:
    tampered = _bundle().model_copy(update={"digest": "0" * 64})

    with pytest.raises(MetricBundlingError, match="digest"):
        hydrate_container_metric(tampered, endpoint_url="http://metric.test")


def test_container_metric_bundler_unbundle_launches_container() -> None:
    launcher = _RecordingContainerLauncher(endpoint_url="http://metric.test")
    bundle = _bundle()

    hydrated = ContainerMetricBundler(builder=_RecordingImageBuilder(), launcher=launcher).unbundle(bundle)

    assert launcher.launched_images == [cast(ContainerMetricPayload, bundle.payload).image]
    assert cast(_HydratedContainerMetric, hydrated).output_spec()[0].name == "score"


async def test_container_metric_client_posts_metric_input_to_score_endpoint() -> None:
    hydrated = cast(_HydratedContainerMetric, hydrate_container_metric(_bundle(), endpoint_url="http://metric.test"))
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(json.loads(request.content))
        assert str(request.url) == "http://metric.test/score"
        return httpx.Response(200, json={"outputs": [{"name": "score", "value": 1.0}]})

    hydrated._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await hydrated.compute_scores(
        MetricInput(
            row=DatasetRow(row_index=0, data={"expected": "blue"}),
            candidate=CandidateOutput(output_text="blue"),
        )
    )

    assert result.outputs[0].name == "score"
    assert result.outputs[0].value == 1.0
    assert issubclass(hydrated.output_spec()[0].value_schema, ContinuousScore)
    assert seen_payloads == [
        {
            "row": {"row_index": 0, "data": {"expected": "blue"}},
            "candidate": {
                "output_text": "blue",
                "response": None,
                "trajectory": None,
                "metadata": {},
            },
        }
    ]


async def test_container_metric_client_includes_container_diagnostics_on_preflight_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(container_module, "_TIMEOUT_SECONDS", 0.01)
    container = _RunningMetricContainer("http://metric.test")
    hydrated = cast(
        _HydratedContainerMetric,
        hydrate_container_metric(_bundle(), container=container),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://metric.test/health"
        return httpx.Response(500)

    hydrated._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    with pytest.raises(MetricBundlingError, match="fake container logs"):
        await hydrated.preflight()


def test_container_payload_validates_from_json_bundle() -> None:
    serialized = _bundle().model_dump(mode="json")

    parsed = MetricBundle.model_validate(serialized)

    assert isinstance(parsed.payload, ContainerMetricPayload)
    assert parsed.payload.kind == "container-http"
