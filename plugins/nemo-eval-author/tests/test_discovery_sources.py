# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which source wins, and what gets read rather than assumed.

Priority is the load-bearing behavior here: the whole artifact is a trust claim, so a repo
offering both a config its author wrote and a layout we could guess at must resolve to the
former, and the report must say which it used.
"""

import json

import yaml
from discovery_fixtures import write_dataset, write_job_dir, write_task, write_wrapper
from nemo_eval_author_plugin.discovery import sources


def _job_config(dataset: str) -> dict:
    return {"agents": [{"name": "oracle"}], "datasets": [{"path": dataset}]}


def test_config_file_outranks_every_inferred_source(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(tmp_path / "jobs" / "run-1", config=_job_config("evals/validation"))
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "eval.yaml").write_text(yaml.safe_dump(_job_config("evals/validation")))

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "config_file"
    chosen = next(item for item in findings if item.name == "config-source")
    assert "config_file" in chosen.message
    # The passed-over sources are named, so a reader can tell what was available.
    assert chosen.hint is not None and "prior_job" in chosen.hint


def test_prior_job_outranks_convention(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(tmp_path / "jobs" / "run-1", config=_job_config("evals/validation"))

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "prior_job"


def test_trial_config_is_not_mistaken_for_a_job_config(tmp_path):
    """Harbor writes config.json and lock.json into trial dirs too, not just job dirs."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(
        tmp_path / "jobs" / "run-1" / "trial-0",
        config={"task": {"path": "evals/validation/task-0"}, "trial_name": "trial-0"},
    )

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "convention"


def test_profile_outranks_convention_and_reads_the_validation_split(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_dataset(tmp_path / "evals" / "train", count=3)
    (tmp_path / "optimizer.yaml").write_text(
        yaml.safe_dump(
            {"agent": "ticket-triage", "datasets": {"train": "evals/train", "validation": "evals/validation"}}
        )
    )

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "profile"
    assert candidate.data["datasets"] == [{"path": str(tmp_path / "evals" / "validation")}]
    split = next(item for item in findings if item.name == "profile-datasets")
    assert "validation" in split.message
    # Evaluating the train split would silently score the set used to optimize.
    assert split.hint is not None and "train" in split.hint


def test_convention_prefers_a_conventional_eval_dir_over_a_larger_one(tmp_path):
    write_dataset(tmp_path / "evals" / "validation", count=2)
    write_dataset(tmp_path / "experiments" / "scratch", count=5)

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["datasets"] == [{"path": str(tmp_path / "evals" / "validation")}]


def test_a_lone_task_template_is_not_a_dataset(tmp_path):
    write_task(tmp_path / "evals" / "task_template")

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is None
    assert any(item.name == "convention-datasets" and item.status == "warn" for item in findings)
    assert any(item.name == "config-source" and item.status == "fail" for item in findings)


def test_wrapper_class_name_is_read_from_the_file(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path, class_name="TicketTriageAgent")

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"import_path": "harbor_wrapper:TicketTriageAgent"}]
    entry = next(item for item in findings if item.name == "agent-entrypoint")
    assert entry.hint is not None and "not assumed" in entry.hint


def test_missing_wrapper_falls_back_to_the_oracle_and_says_what_that_means(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"name": "oracle"}]
    entry = next(item for item in findings if item.name == "agent-entrypoint")
    assert entry.status == "warn"
    assert entry.hint is not None and "evaluates no agent" in entry.hint


def test_env_backend_fills_a_gap_but_never_overrides_a_declaration(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    filled, _ = sources.find_candidate(tmp_path, env_backend="docker")
    assert filled is not None
    assert filled.data["environment"] == {"type": "docker"}

    (tmp_path / "configs").mkdir()
    declared = {**_job_config("evals/validation"), "environment": {"type": "daytona"}}
    (tmp_path / "configs" / "eval.json").write_text(json.dumps(declared))

    respected, _ = sources.find_candidate(tmp_path, env_backend="docker")
    assert respected is not None
    assert respected.data["environment"]["type"] == "daytona"


def test_unreadable_yaml_is_skipped_rather_than_raising(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "broken.yaml").write_text("datasets: [oops\n")

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "convention"
