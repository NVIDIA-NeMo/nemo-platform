# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixtures + marker wiring for customizer GPU e2e tests.

These tests fine-tune small models on a GPU-enabled platform (deployed via Helm),
deploy the result on vLLM, and assert a deterministic base-vs-tuned uplift. They
are heavy and require real GPUs, so every test under ``e2e/customizer/`` is marked:

- ``gpu``            → skipped unless ``--feature gpu`` is passed (keeps them out of CI),
- ``container_only`` → skipped unless ``NMP_BASE_URL`` points at a real platform,
- ``timeout``        → a generous default (training + deploy + eval).

Run them with, e.g.::

    NMP_BASE_URL=http://localhost:30080 \\
      uv run --frozen pytest e2e/customizer --kubernetes --feature gpu --run-e2e -v

The ``sdk`` (module-scoped) and NGC fixtures come from ``e2e/conftest.py``.

Environment knobs:

- ``E2E_N_TRAIN`` / ``E2E_N_VAL``   — dataset slice sizes (default 3000 / 300).
- ``E2E_REQUIRE_UPLIFT=1``          — require strict ``tuned > base`` (default: non-regression).
- ``E2E_GPU_TEST_TIMEOUT``          — per-test timeout seconds (default 5400).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_platform import NeMoPlatform
from nmp.testing.e2e import customizer_datasets as cds

# Dataset slice sizes and the uplift policy — overridable via env for quick runs.
N_TRAIN = int(os.environ.get("E2E_N_TRAIN", "3000"))
N_VAL = int(os.environ.get("E2E_N_VAL", "300"))
REQUIRE_UPLIFT = os.environ.get("E2E_REQUIRE_UPLIFT") == "1"
GPU_TEST_TIMEOUT = int(os.environ.get("E2E_GPU_TEST_TIMEOUT", "5400"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Mark every test under ``e2e/customizer/`` gpu + container_only + a default timeout.

    Applying the gates here (rather than per-file ``pytestmark``) guarantees no
    customizer test can be accidentally left ungated and picked up by CI.
    """
    for item in items:
        if "/e2e/customizer/" not in str(item.fspath):
            continue
        item.add_marker(pytest.mark.gpu)
        item.add_marker(pytest.mark.container_only)
        if item.get_closest_marker("timeout") is None:
            item.add_marker(pytest.mark.timeout(GPU_TEST_TIMEOUT))


@pytest.fixture(scope="session")
def require_uplift() -> bool:
    """Whether tests assert strict uplift (``tuned > base``) vs non-regression."""
    return REQUIRE_UPLIFT


@pytest.fixture(scope="module")
def platform_base_url(sdk: NeMoPlatform) -> str:
    """OpenAI/eval-reachable base URL of the platform under test."""
    return os.environ.get("NMP_BASE_URL") or str(sdk.base_url)


@pytest.fixture(scope="module")
def customizer_workspace(sdk: NeMoPlatform) -> Iterator[str]:
    """A dedicated workspace per test module (shared across parametrized cases)."""
    name = f"e2e-cust-{uuid.uuid4().hex[:8]}"
    sdk.workspaces.create(name=name)
    yield name
    try:
        sdk.workspaces.delete(name)
    except Exception:
        pass  # best-effort teardown


@pytest.fixture(scope="session")
def squad_local(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Download + convert SQuAD to CHAT JSONL once per session (train + val paths)."""
    out = tmp_path_factory.mktemp("squad")
    return cds.prepare_squad_chat_dataset(out, n_train=N_TRAIN, n_val=N_VAL)


@pytest.fixture(scope="session")
def helpsteer_local(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Download HelpSteer3 preference data once per session (training + validation paths)."""
    out = tmp_path_factory.mktemp("helpsteer")
    return cds.prepare_helpsteer_dpo_dataset(out, n_train=N_TRAIN, n_val=N_VAL)
