# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

import pytest
from nemo_experimentalist_plugin.experimentalist.components.evaluator.models import (
    EvaluationResult,
    MetricResult,
    ResourceRef,
    TrialResult,
)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_ROOT = PLUGIN_ROOT / "benchmarks"


def _load_runner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("canonical_benchmark_runner", BENCHMARK_ROOT / "run.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shipped_suite_covers_canonical_count_and_fast_subset() -> None:
    runner = _load_runner()
    suite = runner.load_suite(BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml")
    canonical_ids = set(suite.partitions.quality.all_ids())

    runner.validate_canonical_suite(
        suite,
        canonical_task_ids=canonical_ids,
        resolved_ref=suite.dataset.resolved_ref,
    )

    assert len(suite.partitions.quality.train) == 38
    assert len(suite.partitions.quality.validation) == 25
    assert len(suite.partitions.quality.test) == 26
    assert len(suite.partitions.fast.train) == 35
    assert len(suite.partitions.fast.validation) == 12
    assert len(suite.partitions.fast.test) == 12
    assert "install-windows-3.11" in canonical_ids
    assert "install-windows-3-11" not in canonical_ids


@pytest.mark.parametrize(
    "name",
    ["terminal-bench-smoke.yaml", "terminal-bench-quality.yaml", "tau3-smoke.yaml", "tau3-quality.yaml"],
)
def test_shipped_benchmark_configs_use_current_contracts(name: str) -> None:
    runner = _load_runner()

    config = runner.load_benchmark_config(BENCHMARK_ROOT / "configs" / name)

    assert config.optimizer.evaluator["n_attempts"] >= 1
    assert config.optimizer.eval_author.max_validation_repair_attempts >= 0


def test_task_id_prefix_scopes_canonical_set_to_domain() -> None:
    runner = _load_runner()
    suite = runner.SuiteSpec.model_validate(
        {
            "schema_version": 1,
            "dataset": {
                "name": "sierra-research/tau3-bench",
                "ref": "1",
                "resolved_ref": "sha256:abc",
                "registry_url": "https://hub.harborframework.com",
                "source_url": "https://hub.harborframework.com/datasets/sierra-research/tau3-bench",
                "expected_task_count": 2,
                "task_id_prefix": "pkg__banking-",
            },
            # Partition entries are names inside task_id_prefix, not whole IDs.
            "partitions": {
                "source": {"commit": "deadbeef", "note": "IDs only."},
                "quality": {"train": ["1"], "validation": ["2"], "test": ["3"]},
                "fast": {"train": ["1"], "validation": ["2"], "test": ["3"]},
            },
            "workspace": "tau3-banking",
            "framework_skills": ["nooa"],
        }
    )

    assert suite.partitions.quality.train == ["pkg__banking-1"]

    # Package holds two domains; only the banking three belong to this suite.
    package_ids = {
        "pkg__banking-1",
        "pkg__banking-2",
        "pkg__banking-3",
        "pkg__retail-1",
        "pkg__retail-2",
    }

    with pytest.raises(ValueError, match="expected 2"):
        runner.validate_canonical_suite(suite, canonical_task_ids=package_ids, resolved_ref="sha256:abc")

    suite.dataset.expected_task_count = 3
    scoped = runner.validate_canonical_suite(suite, canonical_task_ids=package_ids, resolved_ref="sha256:abc")

    assert scoped == {"pkg__banking-1", "pkg__banking-2", "pkg__banking-3"}

    # A prefix matching nothing is a manifest bug, not an empty suite.
    suite.dataset.task_id_prefix = "nope-"
    with pytest.raises(ValueError, match="task_id_prefix"):
        runner.validate_canonical_suite(suite, canonical_task_ids=package_ids, resolved_ref="sha256:abc")


def test_suite_resolves_framework_skills_dirs_and_rejects_unknown_ones() -> None:
    runner = _load_runner()
    suite = runner.load_suite(BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml")

    assert suite.workspace == "canonical-terminal-bench-2-1"
    assert suite.framework_skills == ["langchain-framework"]
    assert suite.framework_skills_dirs(PLUGIN_ROOT) == [PLUGIN_ROOT / "framework-skills" / "langchain-framework"]

    suite.framework_skills = ["does-not-exist"]
    with pytest.raises(ValueError, match="does-not-exist"):
        suite.framework_skills_dirs(PLUGIN_ROOT)


def test_user_simulator_exports_task_env_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = _load_runner()
    task_env_names = ("OPENAI_API_KEY", "OPENAI_BASE_URL", "TAU2_USER_MODEL", "TAU2_NL_ASSERTIONS_MODEL")

    def configure(
        api_base: str | None,
        user_simulator: str | None,
        ambient: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Run ``_configure_models`` against a throwaway environ and return what it wrote."""
        environ = {"INFERENCE_API_KEY": "key-123", **(ambient or {})}
        if api_base is not None:
            environ["INFERENCE_API_BASE"] = api_base
        monkeypatch.setattr(os, "environ", environ)
        runner._configure_models(
            runner.ModelSpec(
                aut="a",
                experimentalist_smart="b",
                experimentalist_mid="c",
                experimentalist_fast="d",
                user_simulator=user_simulator,
            )
        )
        return environ

    # Ambient values are seeded to prove the config wins over the developer's shell: a
    # personal OPENAI_API_KEY paired with the gateway base URL would 401, and a stale
    # TAU2_USER_MODEL would silently disagree with the NL-assertion judge.
    exported = configure(
        "https://inference-api.nvidia.com",
        "openai/openai/openai/gpt-5-mini",
        ambient={"OPENAI_API_KEY": "sk-personal", "TAU2_USER_MODEL": "gpt-4o-mini"},
    )

    assert exported["OPENAI_API_KEY"] == "key-123"
    # litellm inside the sidecar needs the /v1 suffix, which INFERENCE_API_BASE lacks.
    assert exported["OPENAI_BASE_URL"] == "https://inference-api.nvidia.com/v1"
    assert exported["TAU2_USER_MODEL"] == "openai/openai/openai/gpt-5-mini"
    assert exported["TAU2_NL_ASSERTIONS_MODEL"] == "openai/openai/openai/gpt-5-mini"

    # A base already carrying /v1, and one with a trailing slash, both normalize to a
    # single suffix; an unset base falls back to the default, which already has one.
    for api_base in ("https://inference-api.nvidia.com/v1/", "https://inference-api.nvidia.com/", None):
        assert configure(api_base, "m")["OPENAI_BASE_URL"] == "https://inference-api.nvidia.com/v1"

    # Suites without a user simulator (Terminal Bench) must not have these set for them.
    without_simulator = configure("https://inference-api.nvidia.com", None)
    assert [name for name in task_env_names if name in without_simulator] == []


def test_suite_validation_rejects_changed_dataset_revision() -> None:
    runner = _load_runner()
    suite = runner.load_suite(BENCHMARK_ROOT / "suites" / "terminal-bench-2.1.yaml")

    with pytest.raises(ValueError, match="resolved to"):
        runner.validate_canonical_suite(
            suite,
            canonical_task_ids=set(suite.partitions.quality.all_ids()),
            resolved_ref="sha256:changed",
        )


def test_evaluation_summary_counts_errors_and_missing_trials_as_zero(tmp_path: Path) -> None:
    runner = _load_runner()
    result_path = tmp_path / "result.json"
    result_path.write_text(
        json.dumps(
            {
                "agent_result": {
                    "n_input_tokens": 10,
                    "n_cache_tokens": 2,
                    "n_output_tokens": 4,
                    "cost_usd": 0.25,
                }
            }
        ),
        encoding="utf-8",
    )
    result = EvaluationResult(
        id="heldout",
        trials=[
            TrialResult(
                id="task-a__0",
                task_id="task-a",
                attempt=0,
                status="completed",
                metrics={"reward": MetricResult(name="reward", value=1.0)},
                resources={"result": ResourceRef(uri=result_path.as_uri())},
            ),
            TrialResult(
                id="task-b__0",
                task_id="task-b",
                attempt=0,
                status="failed",
                metrics={},
                error={"type": "RuntimeError", "message": "failed"},
            ),
        ],
    )

    summary = runner.summarize_evaluation(result, task_count=3, attempts=1)

    assert summary["expected_trials"] == 3
    assert summary["observed_trials"] == 2
    assert summary["missing_trials"] == 1
    assert summary["mean_reward_over_expected"] == pytest.approx(1 / 3)
    assert summary["harness_error_count"] == 2
    assert summary["tokens"] == {"input_tokens": 10, "cache_tokens": 2, "output_tokens": 4}
    assert summary["cost_usd"] == 0.25


def test_optimizer_job_summary_reports_full_trial_and_usage_totals(tmp_path: Path) -> None:
    runner = _load_runner()
    for name, trials, errors, tokens in (
        ("agent-0-train", 4, 1, 100),
        ("agent-1-validation", 2, 0, 50),
    ):
        job_dir = tmp_path / name
        job_dir.mkdir()
        (job_dir / "result.json").write_text(
            json.dumps(
                {
                    "n_total_trials": trials,
                    "stats": {
                        "n_completed_trials": trials,
                        "n_errored_trials": errors,
                        "n_input_tokens": tokens,
                        "n_cache_tokens": tokens // 2,
                        "n_output_tokens": tokens // 4,
                        "cost_usd": 0.1,
                        "evals": {"agent__dataset": {"metrics": [{"mean": 0.5}]}},
                    },
                }
            ),
            encoding="utf-8",
        )

    summary = runner.summarize_experimentalist_jobs(tmp_path)

    assert summary["jobs"] == 2
    assert summary["trials"] == 6
    assert summary["errored_trials"] == 1
    assert summary["input_tokens"] == 150
    assert summary["cost_usd"] == pytest.approx(0.2)
    assert len(summary["job_results"]) == 2
