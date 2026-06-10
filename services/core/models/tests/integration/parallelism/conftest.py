# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fixtures that redirect HuggingFace Hub calls to local config fixtures.

This prevents parallelism integration tests from making real network calls to
huggingface.co, avoiding rate-limit failures in CI.

To regenerate fixtures after adding new models to tests, run:
    uv run python services/core/models/tests/integration/parallelism/download_fixtures.py
"""

from pathlib import Path
from unittest.mock import patch

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _fixture_path(model_id: str) -> Path:
    """Return the local fixture directory for a model ID."""
    return FIXTURES_DIR / model_id


def _has_fixture(model_id: str) -> bool:
    """Check if we have a local fixture for this model."""
    d = _fixture_path(model_id)
    return d.is_dir() and ((d / "config.json").exists() or (d / "model_config.yaml").exists())


def _mock_hf_hub_download(repo_id: str, filename: str, **kwargs):
    """Return path to fixture file instead of downloading from HF Hub."""
    fixture_file = _fixture_path(repo_id) / filename
    if fixture_file.exists():
        return str(fixture_file)
    raise FileNotFoundError(f"Fixture not found: {fixture_file}. Run download_fixtures.py to regenerate.")


_real_auto_config_from_pretrained = None


def _mock_auto_config_from_pretrained(pretrained_model_name_or_path, **kwargs):
    """Redirect remote model IDs to local fixture directories."""
    path_str = str(pretrained_model_name_or_path)
    # Only intercept remote model IDs (not local paths)
    if not Path(path_str).exists() and _has_fixture(path_str):
        return _real_auto_config_from_pretrained(str(_fixture_path(path_str)), **kwargs)
    return _real_auto_config_from_pretrained(pretrained_model_name_or_path, **kwargs)


@pytest.fixture(autouse=True)
def _offline_hf(monkeypatch):
    """Patch HF Hub calls to use local fixtures for all parallelism tests."""
    global _real_auto_config_from_pretrained

    from transformers import AutoConfig

    _real_auto_config_from_pretrained = AutoConfig.from_pretrained

    # Clear the model spec cache so stale entries from prior tests don't bypass our mocks
    from nmp.core.models.parallelism.api import _model_spec_cache

    _model_spec_cache.clear()

    with (
        patch(
            "nmp.core.models.parallelism.models.hf_hub_download",
            side_effect=_mock_hf_hub_download,
        ),
        patch(
            "transformers.AutoConfig.from_pretrained",
            side_effect=_mock_auto_config_from_pretrained,
        ),
    ):
        yield

    _model_spec_cache.clear()
