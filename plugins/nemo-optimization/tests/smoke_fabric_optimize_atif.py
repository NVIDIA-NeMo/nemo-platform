# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in smoke: Fabric optimize study with ATIF trajectory capture.

Requires a reachable OpenAI-compatible inference endpoint and NeMo Fabric + Relay:

  NEMO_FABRIC_REPO=/path/to/NeMo-Fabric \\
  RUN_NEMO_OPTIMIZE_ATIF_E2E=1 \\
  FABRIC_QWEN_BASE_URL=http://10.0.0.51:8080/apis/inference-gateway/v2/workspaces/default/openai/-/v1 \\
  FABRIC_QWEN_MODEL=qwen3-8b-csqa-m16 \\
  uv run --package nemo-optimization-plugin pytest plugins/nemo-optimization/tests/smoke_fabric_optimize_atif.py -q

Install relay support first: ``NEMO_FABRIC_REPO=... script/dev-install-fabric.sh``
(langchain-react uses the ``nemo_relay`` Python SDK mode; the ``nemo-relay`` gateway
binary is not required for this harness).
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest
import yaml
from nemo_optimization.router import OptimizeRouter
from nemo_platform_plugin.job_context import JobContext, StoragePaths
from nemo_platform_plugin.job_results import LocalJobResults

_FABRIC_REPO = Path(os.environ.get("NEMO_FABRIC_REPO", ""))
_BASE_URL = os.environ.get("FABRIC_QWEN_BASE_URL", "")
_MODEL = os.environ.get("FABRIC_QWEN_MODEL", "")
_LIVE_READY = bool(
    os.environ.get("RUN_NEMO_OPTIMIZE_ATIF_E2E") == "1"
    and _FABRIC_REPO.is_dir()
    and _BASE_URL
    and _MODEL
    and importlib.util.find_spec("nemo_fabric") is not None
    and importlib.util.find_spec("nemo_relay") is not None
)

requires_live_optimize_atif = pytest.mark.skipif(
    not _LIVE_READY,
    reason=(
        "set RUN_NEMO_OPTIMIZE_ATIF_E2E=1, NEMO_FABRIC_REPO, FABRIC_QWEN_BASE_URL, "
        "FABRIC_QWEN_MODEL, and install nemo-fabric[relay] (script/dev-install-fabric.sh)"
    ),
)


def _build_payload(dataset_path: Path) -> dict:
    example = _FABRIC_REPO / "examples" / "react-optimize-agent"
    agent = yaml.safe_load((example / "agent.yaml").read_text(encoding="utf-8"))
    profile = yaml.safe_load((example / "profiles" / "qwen-react-native.yaml").read_text(encoding="utf-8"))

    agent["models"]["default"] = {
        "provider": "openai",
        "model": _MODEL,
        "base_url": _BASE_URL,
        "api_key": "not-used",
        "allow_empty_api_key": True,
        "temperature": 0.0,
        "top_p": 1.0,
    }
    agent["models"]["judge"] = {
        "provider": "openai",
        "model": _MODEL,
        "base_url": _BASE_URL,
        "api_key": "not-used",
        "allow_empty_api_key": True,
        "temperature": 0.0,
        "max_tokens": 512,
    }
    agent["eval"] = {
        "general": {"dataset": {"file_path": str(dataset_path)}, "max_concurrency": 1},
        "fabric": {
            "base_dir": str(example),
            "profiles": [profile],
            "capture_trajectory": True,
            "timeout_s": 300,
        },
        "evaluators": {
            "accuracy": {
                "_type": "tunable_rag_evaluator",
                "llm_name": "judge",
                "default_scoring": True,
                "default_score_weights": {"coverage": 0.5, "correctness": 0.3, "relevance": 0.2},
                "judge_llm_prompt": (
                    "Score whether the generated answer correctly addresses the question "
                    "compared to the expected answer. Return JSON only."
                ),
            }
        },
    }
    agent["optimizer"] = {
        "numeric": {"enabled": True, "n_trials": int(os.environ.get("NEMO_OPTIMIZE_ATIF_TRIALS", "2"))},
        "reps_per_param_set": 1,
        "eval_metrics": {
            "average_score": {"evaluator_name": "average_score", "direction": "maximize", "weight": 1.0},
        },
        "search_space": {
            "models.default.temperature": {"values": [0.0, 0.2]},
        },
    }
    return agent


@requires_live_optimize_atif
@pytest.mark.timeout(300)
def test_optimize_study_writes_trial_trace_map(tmp_path: Path) -> None:
    dataset = tmp_path / "rows.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "id": "capital-france",
                    "question": "In one short sentence, what is the capital of France?",
                    "answer": "Answer must state that the capital of France is Paris.",
                }
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    persistent = tmp_path / "persistent"
    ephemeral = tmp_path / "ephemeral"
    persistent.mkdir()
    ephemeral.mkdir()
    ctx = JobContext(
        workspace="default",
        storage=StoragePaths(ephemeral=ephemeral, persistent=persistent),
        results=LocalJobResults(root=persistent / "results"),
    )

    result = OptimizeRouter.dispatch_payload(_build_payload(dataset), ctx=ctx)
    assert result["status"] == "completed"
    assert result["n_trials"] >= 2

    out_dir = persistent / "results" / "optimizer_results"
    summary = json.loads((out_dir / "study_summary.json").read_text(encoding="utf-8"))
    assert summary["experiment_id"]

    trace_map = json.loads((out_dir / "trial_trace_map.json").read_text(encoding="utf-8"))
    assert len(trace_map) >= 2, trace_map
    trial_numbers = {entry["trial_number"] for entry in trace_map}
    assert len(trial_numbers) >= 2, trial_numbers
    for entry in trace_map:
        assert entry["experiment_id"] == summary["experiment_id"]
        assert entry["row_id"] == "capital-france"
        assert entry["trace_format"] == "atif"

    atif_path = Path(trace_map[0]["trace_ref"])
    assert atif_path.is_file(), entry["trace_ref"]
    trajectory = json.loads(atif_path.read_text(encoding="utf-8"))
    assert trajectory.get("steps"), trajectory
