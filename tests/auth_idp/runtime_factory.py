# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Iterable
from typing import cast

import pytest

from tests.auth_idp.providers import load_provider_configs
from tests.auth_idp.runtime_contract import AuthIdpBackend, AuthIdpCase


def iter_auth_idp_cases(
    *,
    backend: AuthIdpBackend | None = None,
    provider_name: str | None = None,
    runtime_id: str | None = None,
    required_capability: str | None = None,
) -> list[AuthIdpCase]:
    cases: list[AuthIdpCase] = []
    for provider in load_provider_configs():
        if provider_name is not None and provider.name != provider_name:
            continue
        for runtime in provider.test_runtimes:
            runtime_backend = cast(AuthIdpBackend, runtime.backend)
            if runtime_id is not None and runtime.id != runtime_id:
                continue
            if backend is not None and runtime_backend != backend:
                continue
            if required_capability is not None and required_capability not in runtime.capabilities:
                continue
            cases.append(
                AuthIdpCase(
                    id=runtime.id,
                    provider=provider,
                    backend=runtime_backend,
                    capabilities=runtime.capabilities,
                    marks=(),
                )
            )
    return cases


def parametrize_cases(cases: Iterable[AuthIdpCase]) -> list[object]:
    return [pytest.param(case, id=case.id, marks=case.marks) for case in cases]


def runtime_class_for_case(case: AuthIdpCase) -> type:
    if case.backend == "compose":
        from tests.auth_idp.runtime_compose import ComposeAuthIdpRuntime

        return ComposeAuthIdpRuntime
    if case.backend == "kubernetes":
        from tests.auth_idp.runtime_kubernetes import KubernetesAuthIdpRuntime

        return KubernetesAuthIdpRuntime
    raise ValueError(f"unsupported auth-idp runtime backend: {case.backend}")
