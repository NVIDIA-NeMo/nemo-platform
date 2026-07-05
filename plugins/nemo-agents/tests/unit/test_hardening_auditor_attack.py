# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from nemo_agents_plugin.hardening.auditor_attack import AuditorAttacker

FIXTURE = Path(__file__).parent / "fixtures" / "hardening" / "sample.hitlog.jsonl"


def _attacker(platform):
    return AuditorAttacker(
        platform,
        probe_spec="promptinject,dan.DanInTheWild",
        seed=1234,
        target_type="nim",
        target_model="agent-under-test",
        target_options={"nim": {"uri": "http://127.0.0.1:8000/v1"}},
        total_attempts=8,
    )


def test_attack_replay_reads_saved_hitlog_without_calling_auditor():
    """Replay parses a saved hitlog, computes the rate, and never invokes Auditor."""
    platform = MagicMock()
    result = _attacker(platform).attack_replay(FIXTURE)
    assert len(result.hits) == 2
    assert result.total_attempts == 8
    assert result.seed == 1234
    assert result.attack_success_rate == 0.25
    assert result.probes == ["promptinject", "dan.DanInTheWild"]
    platform.auditor.run.assert_not_called()


def test_attack_live_builds_config_and_target_then_parses_hitlog():
    """Live mode builds the Auditor config/target (type 'nim', probe_spec, seed) and parses the artifact."""
    platform = MagicMock()
    platform.auditor.run.return_value = {
        "status": "completed",
        "results": {"report-hitlog-jsonl": {"name": "x.hitlog.jsonl", "artifact_url": FIXTURE.as_uri()}},
    }
    result = _attacker(platform).attack_live()

    _, kwargs = platform.auditor.run.call_args
    assert kwargs["config"].plugins.probe_spec == "promptinject,dan.DanInTheWild"
    assert kwargs["config"].run.seed == 1234
    assert kwargs["target"].type == "nim"
    assert kwargs["target"].options["nim"]["uri"] == "http://127.0.0.1:8000/v1"
    assert result.probes == ["promptinject", "dan.DanInTheWild"]
    assert len(result.hits) == 2


def test_download_artifact_resolves_file_url(tmp_path):
    """A file:// artifact URL (what local Auditor runs emit) resolves to the local path."""
    p = tmp_path / "r.hitlog.jsonl"
    p.write_text("{}\n")
    assert _attacker(MagicMock())._download_artifact(p.as_uri()) == p


def test_attack_live_raises_when_no_hitlog_artifact():
    """A scan returning no hitlog artifact is a hard error, not a silent empty result."""
    platform = MagicMock()
    platform.auditor.run.return_value = {"status": "completed", "results": {}}
    with pytest.raises(RuntimeError, match="hitlog"):
        _attacker(platform).attack_live()
