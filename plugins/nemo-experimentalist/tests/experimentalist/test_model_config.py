# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import subprocess
import sys

from nemo_experimentalist_plugin.experimentalist.components.model_config import (
    _client,
    log_model_config,
    model_name,
)


def test_model_name_is_required_per_tier(monkeypatch) -> None:
    """There is no portable default for a model name, so an unset tier must fail here.

    Any built-in default would name a model on exactly one endpoint and be wrong on every
    other, surfacing as an opaque provider error at the first LLM call instead of a
    configuration error before the run starts.
    """
    import pytest

    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://inference-api.nvidia.com/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "k")
    monkeypatch.delenv("EXPERIMENTALIST_SMART_MODEL_NAME", raising=False)

    with pytest.raises(ValueError, match="EXPERIMENTALIST_SMART_MODEL_NAME"):
        model_name("smart")


def test_model_name_reads_its_tier(monkeypatch) -> None:
    monkeypatch.setenv("EXPERIMENTALIST_SMART_MODEL_NAME", "vendor/smart-1")
    monkeypatch.setenv("EXPERIMENTALIST_FAST_MODEL_NAME", "vendor/fast-1")

    assert model_name("smart") == "vendor/smart-1"
    assert model_name("fast") == "vendor/fast-1"


def test_log_model_config_tolerates_unset_tiers(monkeypatch) -> None:
    """A display helper must not be the thing that fails."""
    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://llm.example/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "k")
    for tier in ("SMART", "MID", "FAST"):
        monkeypatch.delenv(f"EXPERIMENTALIST_{tier}_MODEL_NAME", raising=False)

    assert "(unset)" in log_model_config()


def test_model_tiers_cache_on_full_identity() -> None:
    """Repeat identities share a client; a changed key or base does not."""
    _client.cache_clear()
    try:
        first = _client("m", "https://base", "key-1")
        assert _client("m", "https://base", "key-1") is first
        assert _client("m", "https://base", "key-2") is not first
        assert _client("m", "https://other", "key-1") is not first
    finally:
        _client.cache_clear()


def test_importing_components_resolves_no_model() -> None:
    """Importing a component must not build an LLM client.

    Tiers resolve when an agent is constructed, not when its module is imported.
    If this regresses, component modules cannot be imported without credentials --
    which is what registry discovery and ``nemo experimentalist doctor`` require.

    Runs in a subprocess because the client cache is process-global: any earlier
    test that built a client would mask the regression.
    """
    probe = (
        "from nemo_experimentalist_plugin.experimentalist.components import model_config\n"
        "import nemo_experimentalist_plugin.experimentalist.components.loop\n"
        "import nemo_experimentalist_plugin.experimentalist.components.coder\n"
        "import nemo_eval_author_plugin.eval_author.agent\n"
        "info = model_config._client.cache_info()\n"
        "raise SystemExit(0 if info.hits + info.misses == 0 else 1)\n"
    )
    completed = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, f"a model was resolved at import time\n{completed.stderr}"


def test_lazy_model_defers_construction_until_first_use(monkeypatch) -> None:
    """The ``@strategy(llm=...)`` proxy must not touch the environment until used."""
    from nemo_experimentalist_plugin.experimentalist.components.model_config import LazyModel

    monkeypatch.delenv("EXPERIMENTALIST_API_BASE", raising=False)
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY", raising=False)
    proxy = LazyModel("fast")  # constructing it with no credentials must not raise
    assert "unresolved" in repr(proxy)

    monkeypatch.setenv("EXPERIMENTALIST_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("EXPERIMENTALIST_API_KEY", "test-key")
    monkeypatch.setenv("EXPERIMENTALIST_FAST_MODEL_NAME", "vendor/fast-1")
    _client.cache_clear()
    try:
        assert proxy.model == "vendor/fast-1"  # forwards to the real client
        assert "unresolved" not in repr(proxy)
    finally:
        _client.cache_clear()


def test_reward_summary_is_separate_from_the_dimensions() -> None:
    """A scalar rollup must not sit in metrics, where a selector would treat it as a
    dimension that dominates every real one."""
    from nemo_experimentalist_plugin.entities import RewardRecord

    record = RewardRecord(metrics={"node-1": 0.6, "node-2": 0.8}, summary=0.7)

    assert "summary" not in record.metrics
    assert record.summary == 0.7
