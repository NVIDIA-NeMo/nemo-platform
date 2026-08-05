# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent.parent
HELM_DIR = ROOT / "k8s" / "helm"
HELM_TEMPLATE_TIMEOUT_SECONDS = 60


def _helm_template(*args: str) -> list[dict]:
    if shutil.which("helm") is None:
        pytest.skip("helm is required to render the NeMo Platform chart")

    completed = subprocess.run(
        ["helm", "template", "nemo-platform", str(HELM_DIR), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=HELM_TEMPLATE_TIMEOUT_SECONDS,
    )
    return [document for document in yaml.safe_load_all(completed.stdout) if document]


def _clickhouse_resources(documents: list[dict]) -> list[dict]:
    return [
        document
        for document in documents
        if document.get("metadata", {}).get("name") == "nemo-platform-clickhouse"
        or document.get("metadata", {}).get("labels", {}).get("app.kubernetes.io/component") == "clickhouse"
    ]


def _api_container(documents: list[dict]) -> dict:
    deployment = next(
        document
        for document in documents
        if document["kind"] == "Deployment" and document["metadata"]["name"] == "nemo-platform-api"
    )
    return deployment["spec"]["template"]["spec"]["containers"][0]


def _env_by_name(container: dict) -> dict[str, dict]:
    return {env["name"]: env for env in container["env"]}


def test_default_intake_selection_renders_embedded_clickhouse_dependency() -> None:
    documents = _helm_template()

    clickhouse_resources = _clickhouse_resources(documents)
    assert {document["kind"] for document in clickhouse_resources} >= {"Secret", "Service", "StatefulSet"}

    env = _env_by_name(_api_container(documents))
    assert env["NMP_INTAKE_CLICKHOUSE_URL"]["value"] == "http://nemo-platform-clickhouse:8123"


def test_core_service_group_can_skip_embedded_clickhouse_dependency() -> None:
    documents = _helm_template(
        "--set",
        "clickhouse.enabled=false",
        "--set",
        "externalClickhouse.host=unused-clickhouse",
        "--set",
        "externalClickhouse.existingSecret=shared-postgresql",
        "--set",
        "externalClickhouse.existingSecretPasswordKey=nemo-password",
        "--set-string",
        "api.extraArgs[0]=--service-group=core",
    )

    assert _clickhouse_resources(documents) == []
    assert "--service-group=core" in _api_container(documents)["args"]


def test_external_clickhouse_disables_embedded_dependency() -> None:
    documents = _helm_template(
        "--set",
        "clickhouse.enabled=false",
        "--set",
        "externalClickhouse.host=clickhouse.example.internal",
        "--set",
        "externalClickhouse.existingSecret=clickhouse-credentials",
        "--set",
        "externalClickhouse.existingSecretPasswordKey=password",
    )

    assert _clickhouse_resources(documents) == []

    env = _env_by_name(_api_container(documents))
    assert env["NMP_INTAKE_CLICKHOUSE_URL"]["value"] == "http://clickhouse.example.internal:8123"
    password_ref = env["NMP_INTAKE_CLICKHOUSE_PASSWORD"]["valueFrom"]["secretKeyRef"]
    assert password_ref == {"name": "clickhouse-credentials", "key": "password"}
