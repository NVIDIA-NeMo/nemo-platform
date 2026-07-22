# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import pytest

from tests.auth_idp.runtime_factory import iter_auth_idp_cases
from tests.auth_idp.runtime_kubernetes import (
    HELM_UPGRADE_COMMAND_TIMEOUT_SECONDS,
    PORT_FORWARD_READY_TIMEOUT_SECONDS,
    _add_platform_helm_repositories,
    _helm_upgrade_args,
)

pytestmark = [
    pytest.mark.auth_idp,
    pytest.mark.auth_idp_k8s,
    pytest.mark.skipif(
        not any(case.backend == "kubernetes" for case in iter_auth_idp_cases()),
        reason="no Kubernetes auth-idp runtimes are declared",
    ),
]


def test_authentik_kubernetes_runtime_exports_helm_contract_helpers() -> None:
    assert _helm_upgrade_args
    assert _add_platform_helm_repositories
    assert HELM_UPGRADE_COMMAND_TIMEOUT_SECONDS == 900
    assert PORT_FORWARD_READY_TIMEOUT_SECONDS == 30
