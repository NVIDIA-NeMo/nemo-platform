# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import base64
import json
import os
import shlex

import pytest
from nemo_platform_ext.client.tls import client_verify_from_env

from tests.auth_idp.runtime_contract import AuthIdpCase


def jwt_claims(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(payload))
    if not isinstance(decoded, dict):
        return {}
    return decoded


def require_capability(case: AuthIdpCase, capability: str) -> None:
    if capability not in case.capabilities:
        pytest.skip(f"{case.id} does not declare auth-idp capability: {capability}")


def nmp_api_image() -> str:
    registry = os.environ.get("IMAGE_REGISTRY", "my-registry")
    tag = os.environ.get("BAKE_TAG", "local")
    return f"{registry}/nmp-api:{tag}"


def managed_workload_workspace_get_command(*, task_config: dict[str, object] | None = None) -> str:
    command = (
        'if [ -n "${NMP_PRINCIPAL:-}" ]; then '
        "echo 'Unexpected NMP_PRINCIPAL in managed workload'; exit 42; "
        "fi; "
        'if [ -z "${NMP_WORKLOAD_IDENTITY_TOKEN_FILE:-}" ]; then '
        "echo 'Missing NMP_WORKLOAD_IDENTITY_TOKEN_FILE in managed workload'; exit 43; "
        "fi; "
        'if [ ! -f "${NMP_WORKLOAD_IDENTITY_TOKEN_FILE}" ]; then '
        "echo 'Workload identity token file is missing'; exit 44; "
        "fi; "
        "echo 'Workload auth env: NMP_PRINCIPAL=absent NMP_WORKLOAD_IDENTITY_TOKEN_FILE=present'; "
        "exec nemo-platform run task --task nmp.hello_world.tasks.workload_workspace_get"
    )
    if task_config is None:
        return command
    config_json = json.dumps(task_config, separators=(",", ":"))
    return f"{command} --config {shlex.quote(config_json)}"


def runtime_verify(auth_idp_runtime) -> str | bool:
    return getattr(auth_idp_runtime, "verify", client_verify_from_env())
