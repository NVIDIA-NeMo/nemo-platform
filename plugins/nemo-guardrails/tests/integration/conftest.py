# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for the guardrails plugin integration tests.

Re-exports the IGW harness fixtures so test modules don't have to import
them at the top of every file.

- :func:`igw_plugin_harness` — default; no real port for IGW.
- :func:`igw_loopback_harness` — opt-in; IGW additionally bound on a real
  ``127.0.0.1:<port>`` for tests that need IGW's loopback URL.

The module-scope helpers (``_igw_app_context``, ``_igw_loopback_context``,
``_igw_extra_services``) are re-exported here so pytest can discover
them when it resolves :func:`igw_plugin_harness` / :func:`igw_loopback_harness`
within this conftest's scope. ``_igw_extra_services`` is overridden
below to mount :class:`GuardrailsService` on the module-scoped app
once — entity-backed guardrail-config tests in this directory need
its CRUD routes. The previous per-call factory argument
(``igw_loopback_harness(GuardrailsService)``) now raises ``TypeError``
because the module-scoped app is built before the factory runs; mount
via ``_igw_extra_services`` instead.

``HF_HUB_OFFLINE`` is set as a side effect of importing this conftest
(rather than via a function-scoped autouse fixture) so the env var is
in place before pytest builds the module-scoped IGW + Models + Guardrails
app — ``GuardrailsService`` imports drag in ``nemoguardrails`` which
will reach out to HuggingFace if it isn't told to stay offline, and
that happens at module-fixture setup, *before* any function-scoped
fixture runs.
"""

import os

import pytest
from nmp.core.inference_gateway.testing.fixtures import (
    _igw_app_context,
    _igw_loopback_context,
    igw_loopback_harness,
    igw_plugin_harness,
)
from nmp.guardrails.service import GuardrailsService
from nmp.testing.client import ServiceFactory

os.environ.setdefault("HF_HUB_OFFLINE", "1")

__all__ = [
    "_igw_app_context",
    "_igw_loopback_context",
    "igw_loopback_harness",
    "igw_plugin_harness",
]


@pytest.fixture(scope="module")
def _igw_extra_services() -> tuple[ServiceFactory, ...]:
    """Mount :class:`GuardrailsService` on the module-scoped IGW + Models app.

    Overrides the default empty tuple in
    :mod:`nmp.core.inference_gateway.testing.fixtures` so every
    integration test in this directory gets Guardrails CRUD routes,
    whether it uses them or not. The startup cost is amortised across
    the whole module so a test file that only touches inline configs
    pays effectively nothing for the extra service.
    """
    return (GuardrailsService,)
