# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock, patch

import pytest

from nemo_agents_plugin.jobs.harden_agent import HardenAgentConfig, HardenAgentJob


def test_job_metadata():
    """The job advertises the expected name, container, and spec schema."""
    assert HardenAgentJob.name == "harden"
    assert HardenAgentJob.container == "cpu-tasks"
    assert HardenAgentJob.spec_schema is HardenAgentConfig


def test_config_defaults_replay_is_deterministic_default():
    """Replay mode and a fixed seed are the deterministic defaults (Requirement 7)."""
    cfg = HardenAgentConfig(probe_spec="promptinject", judge_model="default/judge")
    assert cfg.rounds == 3
    assert cfg.seed == 1234
    assert cfg.mode == "replay"


def test_replay_mode_requires_hitlog():
    """mode='replay' without a hitlog is rejected up front."""
    cfg = HardenAgentConfig(probe_spec="promptinject", judge_model="default/judge", mode="replay")
    with pytest.raises(ValueError, match="replay_hitlog"):
        cfg.validate_mode()


async def test_compile_builds_single_subprocess_step():
    """compile() returns one subprocess step invoking the harden_agent task module."""
    cfg = HardenAgentConfig(probe_spec="promptinject", judge_model="default/judge", mode="live")
    spec = await HardenAgentJob.compile(
        workspace="default", spec=cfg, entity_client=MagicMock(), job_name=None, async_sdk=MagicMock()
    )
    # compile() returns a dict-shaped spec, accessed by subscript (matches test_improvement_jobs.py).
    assert len(spec["steps"]) == 1
    assert spec["steps"][0]["executor"]["command"] == ["python", "-m", "nemo_agents_plugin.tasks.harden_agent"]


def test_run_wires_loop_from_config():
    """run() builds deps and calls run_hardening_loop with config-derived kwargs, returning serialized state."""
    cfg = {
        "probe_spec": "promptinject",
        "judge_model": "default/judge",
        "mode": "replay",
        "replay_hitlog": "/abs/s.hitlog.jsonl",
        "rounds": 2,
    }
    fake_state = MagicMock()
    group = MagicMock()
    group.id = "grp-xyz"

    with patch("nemo_platform.NeMoPlatform") as platform_cls, \
         patch("nemo_agents_plugin.hardening.loop.run_hardening_loop") as loop, \
         patch("nemo_agents_plugin.hardening._wiring.build_completion_fn"), \
         patch("nemo_agents_plugin.hardening._wiring.build_apply_config"), \
         patch("nemo_agents_plugin.hardening._wiring.build_check"), \
         patch("nemo_agents_plugin.hardening.models._serialize", return_value={"rounds": []}) as ser:
        platform_cls.return_value.experiment_groups.create.return_value = group

        async def _fake_loop(**kwargs):
            _fake_loop.kwargs = kwargs
            return fake_state

        loop.side_effect = _fake_loop
        out = HardenAgentJob().run(cfg, ctx=MagicMock())

    assert out == {"rounds": []}
    ser.assert_called_once_with(fake_state)
    assert _fake_loop.kwargs["max_rounds"] == 2
    assert _fake_loop.kwargs["experiment_group_id"] == "grp-xyz"
    assert _fake_loop.kwargs["replay_hitlog"] is not None


def test_agents_harden_registered_as_job():
    """The agents.harden job is discoverable via the nemo.jobs entry point."""
    from importlib.metadata import entry_points

    names = {ep.name for ep in entry_points(group="nemo.jobs")}
    assert "agents.harden" in names
