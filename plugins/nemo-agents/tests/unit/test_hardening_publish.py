# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
import pytest

from nemo_agents_plugin.hardening.publish import publish_round


class _FakeExperiment:
    def __init__(self, name, id_):
        self.name = name
        self.id = id_


class _FakePlatform:
    """Records the ordered call log so tests can assert create-before-ingest."""

    def __init__(self, *, ingest_fails=False):
        self.calls = []
        self.ingest_kwargs = []
        self._ingest_fails = ingest_fails
        self.experiments = self._Experiments(self)
        self.intake = self._Intake(self)

    class _Experiments:
        def __init__(self, outer):
            self._outer = outer

        async def create(self, **kwargs):
            self._outer.calls.append(("experiment.create", kwargs))
            return _FakeExperiment(name=kwargs["name"], id_="exp-123")

    class _Intake:
        def __init__(self, outer):
            self.ingest = _FakePlatform._IngestNS(outer)

    class _IngestNS:
        def __init__(self, outer):
            self.atif = _FakePlatform._Atif(outer)

    class _Atif:
        def __init__(self, outer):
            self._outer = outer

        async def create(self, **kwargs):
            if self._outer._ingest_fails:
                raise RuntimeError("intake 400: unknown experiment")
            self._outer.calls.append(("atif.create", kwargs))
            self._outer.ingest_kwargs.append(kwargs)


async def test_publish_round_creates_experiment_then_ingests():
    """The experiment is created with the constructed name/dataset/group, before any ingest."""
    platform = _FakePlatform()
    name = await publish_round(
        platform,
        workspace="default",
        experiment_group_id="grp-1",
        round_index=0,
        attack_success_rate=0.25,
        benign_pass_rate=1.0,
        dataset_name="hardening-probes",
        trajectories=[{"test_case_id": "promptinject-0", "steps": [{"source": "agent", "message": "x"}]}],
    )
    assert name == "harden-round-0"
    assert platform.calls[0][0] == "experiment.create"
    create_kwargs = platform.calls[0][1]
    assert create_kwargs["name"] == "harden-round-0"
    assert create_kwargs["dataset_name"] == "hardening-probes"
    assert create_kwargs["workspace"] == "default"
    assert create_kwargs["experiment_group_id"] == "grp-1"
    ingest = platform.ingest_kwargs[0]
    assert ingest["experiment_context"]["experiment_id"] == "exp-123"
    assert ingest["schema_version"].startswith("ATIF-v")
    assert all("step_id" in step for step in ingest["steps"])
    assert ingest["extra"]["verifier_result"]["rewards"] == {"attack_success_rate": 0.25, "benign_pass_rate": 1.0}


async def test_publish_round_ingests_once_per_trajectory():
    """One ATIF ingest is posted per test-case trajectory."""
    platform = _FakePlatform()
    await publish_round(
        platform,
        workspace="default",
        experiment_group_id="grp-1",
        round_index=1,
        attack_success_rate=0.0,
        benign_pass_rate=1.0,
        dataset_name="hardening-probes",
        trajectories=[{"test_case_id": "a", "steps": []}, {"test_case_id": "b", "steps": []}],
    )
    assert sum(1 for name, _ in platform.calls if name == "atif.create") == 2


async def test_publish_round_propagates_ingest_failure():
    """An ingest failure surfaces (no silent swallow)."""
    platform = _FakePlatform(ingest_fails=True)
    with pytest.raises(RuntimeError, match="intake 400"):
        await publish_round(
            platform,
            workspace="default",
            experiment_group_id="grp-1",
            round_index=0,
            attack_success_rate=0.0,
            benign_pass_rate=1.0,
            dataset_name="hardening-probes",
            trajectories=[{"test_case_id": "a", "steps": []}],
        )
