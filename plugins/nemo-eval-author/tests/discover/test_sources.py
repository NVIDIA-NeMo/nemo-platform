# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Which source wins, and what gets read rather than assumed.

Priority is the load-bearing behavior here: the whole artifact is a trust claim, so a repo
offering both a config its author wrote and a layout we could guess at must resolve to the
former, and the report must say which it used.
"""

import yaml
from harbor.models.job.config import JobConfig
from harbor_fixtures import write_dataset, write_job_dir, write_task, write_wrapper
from nemo_eval_author_plugin.discovery import sources
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import _AGENT_IMPORT_ROOT
from nemo_experimentalist_plugin.resolve import classify_dataset_value


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


def test_an_optimizer_job_dir_is_not_read_as_the_repo_s_own_setup(tmp_path):
    """Experimentalist writes config.json and lock.json into its own results directory.

    Harbor really did resolve and run that config, which is what makes it outrank the profile.
    But its agent import path names a package Experimentalist synthesizes in ``sys.modules``
    for the duration of its run, so no separate ``harbor`` process can import it: running the
    optimizer and then discover reported "Harbor cannot run this repo's evals" about a repo
    that had just been evaluated successfully.
    """
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(
        tmp_path / ".nemo-optimizer" / "experiments" / "run-1" / "eval-and-optimize" / "results" / "job-1",
        config={
            "agents": [{"import_path": "_nemo_experimentalist_eval_agents.agent_abc123:WrappedAgent"}],
            "datasets": [{"path": "evals/validation"}],
        },
    )

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "convention"
    assert not any(item.name == "prior-job" for item in findings)


def test_a_synthetic_agent_import_path_is_rejected_wherever_it_is_found(tmp_path):
    """The pruned directories are Experimentalist's defaults, not a promise about the layout."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(
        tmp_path / "elsewhere" / "job-1",
        config={
            "agents": [{"import_path": f"{_AGENT_IMPORT_ROOT}.src_agent_deadbeef:WrappedAgent"}],
            "datasets": [{"path": "evals/validation"}],
        },
    )

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "convention"


def test_a_real_prior_job_is_still_the_stronger_source(tmp_path):
    """The guard is about synthetic import paths, not about distrusting prior jobs."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(
        tmp_path / "jobs" / "run-1",
        config={
            "agents": [{"import_path": "harbor_wrapper:WrappedAgent"}],
            "datasets": [{"path": "evals/validation"}],
        },
    )

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "prior_job"


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


def test_a_registry_dataset_ref_is_passed_to_harbor_as_a_ref(tmp_path):
    """A ref is a name Harbor downloads, not a directory under the profile.

    ``resolve_profile_path`` has no registry awareness, so it turned
    ``tau2-bench-live-validation@1.0`` into ``<profile-dir>/tau2-bench-live-validation@1.0`` and
    ``Job.create`` raised ``FileNotFoundError`` — discover reporting "cannot run" about a
    profile the optimizer runs every day.
    """
    (tmp_path / "optimizer.yaml").write_text(
        yaml.safe_dump(
            {
                "agent": "nemo-oo-airline",
                "datasets": {
                    "train": "tau2-bench-live-train@1.0",
                    "validation": "tau2-bench-live-validation@1.0",
                    "registry_url": "https://registry.example/registry.json",
                },
            }
        )
    )

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "profile"
    assert candidate.data["datasets"] == [
        {
            "name": "tau2-bench-live-validation",
            "version": "1.0",
            "registry_url": "https://registry.example/registry.json",
        }
    ]
    # Harbor is the judge of whether that names a dataset it can fetch.
    assert JobConfig.model_validate(candidate.data).datasets[0].is_registry()
    split = next(item for item in findings if item.name == "profile-datasets")
    assert split.status == "warn"
    assert "registry ref" in split.message
    assert split.hint is not None and "reachable" in split.hint


def test_a_local_dataset_path_is_unaffected_by_a_declared_registry(tmp_path):
    """An explicit relative path stays a path, which is the rule Experimentalist applies."""
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "optimizer.yaml").write_text(
        yaml.safe_dump(
            {
                "datasets": {
                    "validation": "./evals/validation",
                    "registry_url": "https://registry.example/registry.json",
                }
            }
        )
    )

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["datasets"] == [{"path": str(tmp_path / "evals" / "validation")}]
    assert next(item for item in findings if item.name == "profile-datasets").status == "pass"


def test_the_dataset_classifier_agrees_with_experimentalist(tmp_path):
    """The copy exists to keep the plugin boundary shrinking, not to hold a second opinion.

    Both plugins read the same ``optimizer.yaml``. A value the optimizer downloads and discover
    resolves as a path would produce an artifact describing a directory nobody has.
    """
    (tmp_path / "local-dir").mkdir()
    values = [
        "./evals/validation",
        "../sibling/evals",
        "/absolute/evals",
        "~/evals",
        "local-dir",
        "not-on-disk",
        "namespaced/dataset",
        "tau2-bench-live-validation@1.0",
    ]

    for registry_url in (None, "https://registry.example/registry.json"):
        ours = [sources.classify_dataset_value(value, tmp_path, registry_url=registry_url) for value in values]
        theirs = [classify_dataset_value(value, tmp_path, registry_url=registry_url) for value in values]
        assert ours == theirs, f"classifiers disagree with registry_url={registry_url}"


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


def test_a_wrapper_at_the_repo_root_is_importable_from_the_root(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path)

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.agent_search_path == "."


def test_a_nested_wrapper_records_the_directory_the_import_path_omits(tmp_path):
    """``harbor_wrapper:WrappedAgent`` is where the module is *not*, which is the whole problem.

    The wrapper is found by walking, so it can be anywhere; the import path Harbor takes is a
    bare module name. Without the directory beside it, ``harbor job start -c`` fails with
    ``No module named 'harbor_wrapper'`` on a config discovery called runnable.
    """
    write_dataset(tmp_path / "evals" / "validation")
    write_wrapper(tmp_path / "src" / "myagent")

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"import_path": "harbor_wrapper:WrappedAgent"}]
    assert candidate.agent_search_path == "src/myagent"
    entry = next(item for item in findings if item.name == "agent-entrypoint")
    assert "src/myagent" in entry.message, "a reader has to be able to see where it is imported from"


def test_a_builtin_agent_needs_no_search_path(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"name": "oracle"}]
    assert candidate.agent_search_path is None


def test_missing_wrapper_falls_back_to_the_oracle_and_says_what_that_means(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"name": "oracle"}]
    entry = next(item for item in findings if item.name == "agent-entrypoint")
    assert entry.status == "warn"
    assert "No harbor_wrapper.py found" in entry.message
    assert entry.hint is not None and "evaluates no agent" in entry.hint


def test_a_wrapper_whose_class_was_not_recognized_is_not_reported_as_a_missing_file(tmp_path):
    """The oracle silently replaces the agent, so the reason has to be the true one.

    The class is matched by the base name in the source, so a duck-typed wrapper falls through
    to the oracle — which replays ``solution/solve.sh`` and evaluates nothing. Reporting that
    as "No harbor_wrapper.py found" sends the author looking for a file that is right there.
    """
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "agent" / "nested").mkdir(parents=True)
    (tmp_path / "agent" / "nested" / "harbor_wrapper.py").write_text(
        "class WrappedAgent:\n    async def run(self, instruction, environment):\n        return None\n"
    )

    candidate, findings = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["agents"] == [{"name": "oracle"}]
    entry = next(item for item in findings if item.name == "agent-entrypoint")
    assert entry.status == "warn"
    assert "No harbor_wrapper.py found" not in entry.message
    assert "agent/nested/harbor_wrapper.py" in entry.message
    assert "BaseAgent" in entry.message and "BaseInstalledAgent" in entry.message
    assert entry.hint is not None and "evaluates no agent" in entry.hint


def test_a_config_file_is_read_as_written_and_stays_owned_by_the_repo(tmp_path):
    """Nothing is injected into a config someone maintains, so the artifact can point at it.

    The environment backend is the case that tempts a default: assembly leaves it alone and
    lets Harbor apply its own, rather than writing a value into a payload the repo's file
    does not contain.
    """
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "configs").mkdir()
    declared = {**_job_config("evals/validation"), "environment": {"type": "daytona"}}
    (tmp_path / "configs" / "eval.yaml").write_text(yaml.safe_dump(declared))

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.data["environment"] == {"type": "daytona"}
    assert candidate.source.owns_file is True


def test_an_undeclared_backend_is_left_for_harbor_to_default(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert "environment" not in candidate.data


def test_an_inferred_source_never_claims_a_file_it_could_be_run_from(tmp_path):
    """A prior job's config.json is Harbor's own output record, not an input anyone maintains."""
    write_dataset(tmp_path / "evals" / "validation")
    write_job_dir(tmp_path / "jobs" / "run-1", config=_job_config("evals/validation"))

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.path is not None
    assert candidate.source.owns_file is False


def test_unreadable_yaml_is_skipped_rather_than_raising(tmp_path):
    write_dataset(tmp_path / "evals" / "validation")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "broken.yaml").write_text("datasets: [oops\n")

    candidate, _ = sources.find_candidate(tmp_path)

    assert candidate is not None
    assert candidate.source.kind == "convention"
