# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Pytest fixtures for the guardrails plugin integration tests.

Re-exports the IGW harness fixtures so test modules don't have to import
them at the top of every file, and provides an autouse fixture that
keeps ``nemoguardrails`` from reaching out to HuggingFace at startup.

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
(``igw_loopback_harness(GuardrailsService)``) now emits a
``DeprecationWarning`` because the module-scoped app is built before
the factory runs; mount via ``_igw_extra_services`` instead.
"""

import pytest
from nmp.core.inference_gateway.testing.fixtures import (
    _igw_app_context,
    _igw_loopback_context,
    igw_loopback_harness,
    igw_plugin_harness,
)
from nmp.guardrails.service import GuardrailsService
from nmp.testing.client import ServiceFactory

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


@pytest.fixture(autouse=True)
def offline_huggingface(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip ``nemoguardrails`` HuggingFace tokenizer downloads — they time out offline."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
