# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import sys
import textwrap

import pytest
from nemo_experimentalist_plugin.experimentalist.components.model_config import (
    _client,
    api_base,
    api_key,
    log_model_config,
    model_name,
)
from nemo_experimentalist_plugin.settings import ExperimentalistConfig, ModelsConfig
from nemo_platform_plugin.config import NMP_CONFIG_FILE_PATH_ENV_VAR, Configuration

# Only the tests that assert on *where* a value comes from touch the environment. Everything
# else injects the settings object, which is both closer to what the code reads and immune
# to an ``/etc/nmp/config.yaml`` existing on the machine running the suite.
TIER_ENV = {
    "smart": "NEMO_EXPERIMENTALIST_MODELS_SMART",
    "mid": "NEMO_EXPERIMENTALIST_MODELS_MID",
    "fast": "NEMO_EXPERIMENTALIST_MODELS_FAST",
}


def _configure(**kwargs) -> None:
    """Install settings directly, bypassing both the environment and any config file.

    The environment has to be cleared first, and that is not belt-and-braces: this plugin's
    settings are env-first by design, so ``ExperimentalistConfig(models=...)`` would read
    conftest's import-time placeholders over the values passed here. The autouse fixture in
    ``conftest`` snapshots and restores ``os.environ``, so removing them is safe.
    """
    for name in [n for n in os.environ if n.startswith("NEMO_EXPERIMENTALIST_")]:
        del os.environ[name]
    Configuration.set_override(ExperimentalistConfig(**kwargs))


def _configured(base: str = "https://llm.example/v1", key: str = "k", **tiers) -> None:
    """The common case: a usable endpoint plus whichever tiers the test names."""
    _configure(api_base=base, api_key=key, models=ModelsConfig(**tiers))


def test_model_name_is_required_per_tier() -> None:
    """There is no portable default for a model name, so an unset tier must fail here.

    Any built-in default would name a model on exactly one endpoint and be wrong on every
    other, surfacing as an opaque provider error at the first LLM call instead of a
    configuration error before the run starts.
    """
    _configured(base="https://inference-api.nvidia.com/v1")

    with pytest.raises(ValueError, match=TIER_ENV["smart"]):
        model_name("smart")


def test_model_name_reads_its_tier() -> None:
    _configured(smart="vendor/smart-1", fast="vendor/fast-1")

    assert model_name("smart") == "vendor/smart-1"
    assert model_name("fast") == "vendor/fast-1"


def test_unknown_tier_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown model tier"):
        model_name("enormous")


def test_log_model_config_tolerates_unset_tiers() -> None:
    """A display helper must not be the thing that fails."""
    _configured()

    assert "(unset)" in log_model_config()


def test_log_model_config_survives_a_wholly_unconfigured_install() -> None:
    """The banner must not raise on the install it exists to diagnose.

    ``_shown`` always guarded the tiers, but the endpoint and key were resolved
    unguarded, so the one case where you most want to see the banner was the one case
    that raised.
    """
    _configure()

    rendered = log_model_config()

    assert rendered.count("(unset)") == 5


def test_log_model_config_masks_the_key() -> None:
    """The banner is printed to logs, so it must never carry the whole credential."""
    _configured(key="sk-abcdefghijkl")

    rendered = log_model_config()

    assert "sk-abcdefghijkl" not in rendered
    assert "ijkl" in rendered


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


# ---------------------------------------------------------------------------
# Where settings come from
# ---------------------------------------------------------------------------


def _write_platform_config(tmp_path, monkeypatch, body: str):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(body))
    monkeypatch.setenv(NMP_CONFIG_FILE_PATH_ENV_VAR, str(path))
    Configuration.clear_cache()
    return path


def test_settings_come_from_the_platform_config_file(tmp_path, monkeypatch) -> None:
    """Model tiers and endpoint are deployment settings, so the config file can supply them."""
    for name in (*TIER_ENV.values(), "NEMO_EXPERIMENTALIST_API_BASE", "NEMO_EXPERIMENTALIST_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    _write_platform_config(
        tmp_path,
        monkeypatch,
        """
        experimentalist:
          api_base: https://from-file.example/v1
          api_key: file-key
          models:
            smart: vendor/from-file
        """,
    )

    assert api_base() == "https://from-file.example/v1"
    assert api_key() == "file-key"
    assert model_name("smart") == "vendor/from-file"


def test_environment_overrides_the_config_file(tmp_path, monkeypatch) -> None:
    """The platform's precedence, which this plugin now follows: env beats file beats default.

    This is the inverse of the old behaviour, where a config block was written into the
    environment and so silently won over anything the operator had exported.
    """
    _write_platform_config(
        tmp_path,
        monkeypatch,
        """
        experimentalist:
          api_base: https://from-file.example/v1
          models:
            smart: vendor/from-file
        """,
    )
    monkeypatch.setenv("NEMO_EXPERIMENTALIST_API_BASE", "https://from-env.example/v1")
    monkeypatch.setenv(TIER_ENV["smart"], "vendor/from-env")
    Configuration.clear_cache()

    assert api_base() == "https://from-env.example/v1"
    assert model_name("smart") == "vendor/from-env"


def test_api_key_is_not_exposed_by_repr() -> None:
    """A settings object gets logged; the credential inside it must not come along."""
    _configured(key="sk-not-in-the-logs")

    assert "sk-not-in-the-logs" not in repr(ExperimentalistConfig.get())


def test_reward_summary_is_separate_from_the_dimensions() -> None:
    """A scalar rollup must not sit in metrics, where a selector would treat it as a
    dimension that dominates every real one."""
    from nemo_experimentalist_plugin.entities import RewardRecord

    record = RewardRecord(metrics={"node-1": 0.6, "node-2": 0.8}, summary=0.7)

    assert "summary" not in record.metrics
    assert record.summary == 0.7


def test_record_reward_merges_rather_than_replaces() -> None:
    """A second writer must not drop what the first measured.

    No production path writes a channel twice today, so nothing else would catch a
    change to replace semantics — but the channel set is open by design, and the loss
    would be silent.
    """
    from doubles import make_candidate

    candidate = make_candidate(label="agent-0", description="baseline")
    candidate.record_reward("insight", metrics={"reward": 0.5})
    candidate.record_reward("insight", metadata={"suite_identity": "sha256:abc"})

    record = candidate.reward("insight")
    assert record.metrics == {"reward": 0.5}
    assert record.metadata == {"suite_identity": "sha256:abc"}


def test_an_unmeasured_channel_is_distinguishable_from_an_empty_one() -> None:
    """``reward()`` erases the difference on purpose; ``in`` is how you ask.

    Eight call sites gate evaluation on ``channel not in candidate.rewards``, so a
    read must never make a channel appear measured. This is why the mapping cannot
    become a ``defaultdict``, whose ``__missing__`` inserts.
    """
    from doubles import make_candidate

    candidate = make_candidate(label="agent-0", description="baseline")

    assert candidate.reward("train").metrics == {}
    assert "train" not in candidate.rewards
