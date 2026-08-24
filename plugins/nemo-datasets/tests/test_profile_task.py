# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the dataset-profiler job task."""

import json
from pathlib import Path
from typing import cast

import nemo_datasets_plugin.tasks.profile.run as run_mod
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from nemo_datasets_plugin.profiler.file_source import LocalFileSource
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.job_results import ResultRef
from nemo_platform_plugin.jobs.constants import (
    NEMO_JOB_FILESET_ENVVAR,
    NEMO_JOB_ID_ENVVAR,
    NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR,
    NEMO_JOB_WORKSPACE_ENVVAR,
)

# The task touches the sdk only through PlatformJobResults and the Files client, both patched below,
# so a bare object stands in for it.
_SDK = cast(NeMoPlatform, object())


def _dataset(root: Path, rows=None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    rows = rows or [{"q": "why?", "a": "because #### 4"}]
    pq.write_table(pa.Table.from_pylist(rows), root / "train-00000-of-00001.parquet")
    return root


def _install(monkeypatch, tmp_path: Path, config: dict, data: Path | None = None) -> dict:
    """Point the task at a step config, stand in for the fileset download, and capture what it writes.

    ``published`` collects the job artifact; ``persisted`` collects what landed on the fileset. Both
    stay empty when the task bails, which is what the failure tests assert on.
    """
    published: dict = {}

    def _source(client, *, workspace, fileset):
        published["read"] = (workspace, fileset)
        if data is None:
            raise RuntimeError("fileset could not be read")
        return LocalFileSource(data)

    class _Results:
        def __init__(self, *, job_name, workspace, sdk):
            published.update(job_name=job_name, workspace=workspace)

        def save(self, name, local_path):
            published["name"] = name
            published["profile"] = json.loads((Path(local_path) / "profile.json").read_text())
            return ResultRef(name=name, artifact_url=f"file://{local_path}")

    class _FilesClient:
        def put_fileset_profile(self, *, workspace, name, body):
            published["stored"] = (workspace, name, body)

    config_path = tmp_path / "step-config.json"
    config_path.write_text(json.dumps(config))
    monkeypatch.setenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR, str(config_path))
    monkeypatch.setenv(NEMO_JOB_WORKSPACE_ENVVAR, "ws1")
    monkeypatch.setenv(NEMO_JOB_ID_ENVVAR, "job-1")
    monkeypatch.delenv(NEMO_JOB_FILESET_ENVVAR, raising=False)
    monkeypatch.setattr(run_mod, "FilesetFileSource", _source)
    monkeypatch.setattr(run_mod, "PlatformJobResults", _Results)
    monkeypatch.setattr(run_mod, "client_from_platform", lambda sdk, client_cls: _FilesClient())
    return published


def test_task_profiles_a_fileset_and_publishes_the_profile(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data")
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1"}, data)

    assert run_mod.run(_SDK) == 0

    assert published["read"] == ("ws1", "fs1")
    assert published["job_name"] == "job-1"
    assert published["workspace"] == "ws1"
    assert published["name"] == "profile"
    profile = published["profile"]
    assert profile["partitions"][0]["file_formats"] == ["parquet"]
    assert profile["coverage"]["files_read"] == 1


def test_task_stores_the_profile_against_the_fileset(tmp_path, monkeypatch):
    # A single PUT of just the profile: nothing else on the fileset is read, so an unrelated metadata
    # edit landing mid-run cannot be clobbered by it.
    data = _dataset(tmp_path / "data")
    published = _install(
        monkeypatch, tmp_path, {"fileset": "fs1", "column_roles": {"q": "prompt", "a": "completion"}}, data
    )

    assert run_mod.run(_SDK) == 0

    workspace, name, body = published["stored"]
    assert (workspace, name) == ("ws1", "fs1")
    assert body.profile.partitions[0].classification.dataset_type == "prompt_completion"


def test_task_reads_the_fileset_in_place(tmp_path, monkeypatch):
    # Nothing is staged on disk: the source is handed the fileset and reads it through the Files API,
    # so there is no download to clean up and the task's cost tracks the read, not the fileset size.
    data = _dataset(tmp_path / "data")
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1"}, data)

    assert run_mod.run(_SDK) == 0
    assert published["read"] == ("ws1", "fs1")


def test_task_prefers_the_step_configs_workspace_over_the_environment(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data")
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1", "workspace": "explicit"}, data)

    assert run_mod.run(_SDK) == 0
    assert published["workspace"] == "explicit"


def test_task_passes_column_role_hints_to_the_profiler(tmp_path, monkeypatch):
    # The step config is the profiler's hint channel now that there is no CLI to carry --column-role.
    data = _dataset(tmp_path / "data")
    published = _install(
        monkeypatch, tmp_path, {"fileset": "fs1", "column_roles": {"q": "prompt", "a": "completion"}}, data
    )

    assert run_mod.run(_SDK) == 0
    classification = published["profile"]["partitions"][0]["classification"]
    # `primary` is derived and deliberately not serialized, so the stored shape is the list alone.
    assert classification["candidates"] == ["prompt_completion"]
    assert "dataset_type" not in classification


def test_task_reads_everything_by_default(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data")
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1"}, data)

    assert run_mod.run(_SDK) == 0
    coverage = published["profile"]["coverage"]
    assert coverage["rows_scanned"] == coverage["rows_present"]  # nothing left unread


def test_task_honours_an_explicit_row_budget(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data", rows=[{"a": i} for i in range(20)])
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1", "row_budget": 5}, data)

    assert run_mod.run(_SDK) == 0
    assert published["profile"]["coverage"]["rows_scanned"] == 5


def test_row_budget_zero_asks_for_every_row(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data", rows=[{"a": i} for i in range(20)])
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1", "row_budget": 0}, data)

    assert run_mod.run(_SDK) == 0
    coverage = published["profile"]["coverage"]
    assert coverage["rows_scanned"] == coverage["rows_present"]  # 0 means "all of them"
    assert published["profile"]["partitions"][0]["rows_complete"] is True


def test_task_fails_when_the_step_config_says_nothing_to_profile(tmp_path, monkeypatch):
    published = _install(monkeypatch, tmp_path, {}, _dataset(tmp_path / "data"))
    assert run_mod.run(_SDK) == 1  # a nonzero exit, not a traceback out of the container
    assert "profile" not in published


def test_task_fails_when_the_fileset_cannot_be_read(tmp_path, monkeypatch):
    published = _install(monkeypatch, tmp_path, {"fileset": "fs1"}, data=None)

    assert run_mod.run(_SDK) == 1
    assert "profile" not in published


def test_task_fails_without_a_step_config(tmp_path, monkeypatch):
    _install(monkeypatch, tmp_path, {"fileset": "fs1"}, _dataset(tmp_path / "data"))
    monkeypatch.delenv(NEMO_JOB_STEP_CONFIG_FILE_PATH_ENVVAR)
    assert run_mod.run(_SDK) == 1


def test_task_rejects_a_negative_row_budget(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data")
    _install(monkeypatch, tmp_path, {"fileset": "fs1", "row_budget": -1}, data)
    assert run_mod.run(_SDK) == 1


@pytest.mark.parametrize("budget", [1.9, True, False, "5"], ids=["fraction", "true", "false", "string"])
def test_task_rejects_a_row_budget_that_is_not_an_integer(tmp_path, monkeypatch, budget):
    # `int()` accepted all four and changed what three of them meant: 1.9 profiled one row, `true`
    # profiled one row, and `false` became 0, which this task reads as "every row". A budget that
    # quietly means something else than the config says is worse than a job that refuses to start.
    data = _dataset(tmp_path / "data")
    _install(monkeypatch, tmp_path, {"path": str(data), "row_budget": budget})
    assert run_mod.run(_SDK) == 1


def test_task_rejects_column_roles_that_are_not_a_mapping(tmp_path, monkeypatch):
    data = _dataset(tmp_path / "data")
    _install(monkeypatch, tmp_path, {"fileset": "fs1", "column_roles": ["q=prompt"]}, data)
    assert run_mod.run(_SDK) == 1
