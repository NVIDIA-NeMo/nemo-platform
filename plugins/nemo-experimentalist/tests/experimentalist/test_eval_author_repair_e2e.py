# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Real-model canaries for Eval Author-authored Harbor verifiers."""

import asyncio
import json
import os
from pathlib import Path

import pytest
from nemo_experimentalist_plugin.eval_author.agent import EvalAuthor
from nemo_experimentalist_plugin.eval_author.models import EvalAuthorConfig
from nemo_experimentalist_plugin.experimentalist.components.evaluator import (
    DatasetValidationError,
    local_path_from_uri,
)
from nemo_experimentalist_plugin.experimentalist.components.evaluator.harbor import (
    HarborDataset,
    HarborEvaluator,
    HarborEvaluatorConfig,
)
from nemo_experimentalist_plugin.experimentalist.components.model_config import get_fast_model
from nemo_experimentalist_plugin.experimentalist.components.trace_analyzer import Diagnostic
from nemo_insights_plugin.entities import Insight

_HAS_EXPERIMENTALIST_LLM = bool(
    os.environ.get("EXPERIMENTALIST_API_BASE") and os.environ.get("EXPERIMENTALIST_API_KEY")
)
_RUN_EVAL_AUTHOR_REPAIR_E2E = os.environ.get("RUN_EVAL_AUTHOR_REPAIR_E2E") == "1"
_RUN_EVAL_AUTHOR_HARBOR_E2E = os.environ.get("RUN_EVAL_AUTHOR_HARBOR_E2E") == "1"
_MALFORMED_VERIFIER = """\
def check_tool_hallucination() -> float:
    try:
        return 1.0
"""
_KNOWN_FAILING_TRACE = {
    "resourceSpans": [
        {
            "scopeSpans": [
                {
                    "spans": [
                        {
                            "name": "generate_response",
                            "attributes": [
                                {
                                    "key": "openinference.span.kind",
                                    "value": {"stringValue": "CHAIN"},
                                },
                                {
                                    "key": "output.value",
                                    "value": {
                                        "stringValue": (
                                            "The Denver warehouse has eight units available. "
                                            "I answered from memory without consulting inventory."
                                        )
                                    },
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    ]
}


def _write_malformed_task(dataset_dir: Path, task_id: str) -> None:
    task_dir = dataset_dir / task_id
    verifier_dir = task_dir / "tests"
    verifier_dir.mkdir(parents=True)
    (task_dir / "task.toml").write_text(f'[task]\nname = "local/{task_id}"\n', encoding="utf-8")
    (verifier_dir / "test.sh").write_text(
        "#!/usr/bin/env bash\npython /tests/check_tool_hallucination.py\n",
        encoding="utf-8",
    )
    (verifier_dir / "check_tool_hallucination.py").write_text(_MALFORMED_VERIFIER, encoding="utf-8")


def _write_known_failing_task(dataset_dir: Path) -> None:
    task_dir = dataset_dir / "known-failing-inventory-lookup"
    tests_dir = task_dir / "tests"
    environment_dir = task_dir / "environment"
    tests_dir.mkdir(parents=True)
    environment_dir.mkdir()
    (task_dir / "task.toml").write_text(
        """\
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
version = "1.0"

[task]
name = "local/known-failing-inventory-lookup"

[verifier]
timeout_sec = 60.0

[agent]
timeout_sec = 60.0

[environment]
build_timeout_sec = 300.0
cpus = 1
memory_mb = 512
storage_mb = 1024
gpus = 0
network_mode = "no-network"
mcp_servers = []

[verifier.env]

[solution.env]
""",
        encoding="utf-8",
    )
    (task_dir / "instruction.md").write_text(
        "Use the inventory_lookup tool before reporting how many units are available in the Denver warehouse.\n",
        encoding="utf-8",
    )
    (environment_dir / "Dockerfile").write_text(
        """\
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
FROM python:3.12-slim
WORKDIR /app
""",
        encoding="utf-8",
    )
    (tests_dir / "test.sh").write_text(
        """\
#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail
mkdir -p /logs/verifier
printf '{"reward": 1.0}\n' > /logs/verifier/reward.json
""",
        encoding="utf-8",
    )


def _write_known_failing_agent(agent_dir: Path) -> None:
    agent_dir.mkdir()
    trace_payload = json.dumps(_KNOWN_FAILING_TRACE, separators=(",", ":"))
    (agent_dir / "harbor_wrapper.py").write_text(
        f"""\
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import shlex

from harbor import AgentContext, BaseAgent, BaseEnvironment


class WrappedAgent(BaseAgent):
    @staticmethod
    def name() -> str:
        return "known-failing-baseline"

    def version(self) -> str:
        return "1.0.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        pass

    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        trace_payload = {trace_payload!r}
        command = (
            "mkdir -p /logs/artifacts/traces && "
            f"printf '%s\\\\n' {{shlex.quote(trace_payload)}} "
            "> /logs/artifacts/traces/trace.jsonl"
        )
        process = await environment.exec(command)
        context.metadata = {{
            "instruction": instruction,
            "stdout": process.stdout,
            "stderr": process.stderr,
            "returncode": process.return_code,
        }}
        if process.return_code != 0:
            raise RuntimeError(process.stderr or process.stdout)
""",
        encoding="utf-8",
    )


@pytest.mark.skipif(
    not (_RUN_EVAL_AUTHOR_REPAIR_E2E and _HAS_EXPERIMENTALIST_LLM),
    reason=(
        "Set RUN_EVAL_AUTHOR_REPAIR_E2E=1 with EXPERIMENTALIST_API_BASE and EXPERIMENTALIST_API_KEY to run the Eval Author repair canary."
    ),
)
async def test_gpt5_mini_repairs_malformed_harbor_verifiers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GPT-5 mini repairs try-without-except failures across an Insight suite."""
    insight_suite_dir = tmp_path / "insight-suite"
    _write_malformed_task(insight_suite_dir, "task-a")
    _write_malformed_task(insight_suite_dir, "task-b")
    insight_suite = HarborDataset.from_path(insight_suite_dir)

    with pytest.raises(DatasetValidationError) as exc_info:
        await insight_suite.validate()

    validation_feedback = str(exc_info.value)
    assert "task 'task-a'" in validation_feedback
    assert "task 'task-b'" in validation_feedback
    assert "SyntaxError: expected 'except' or 'finally' block" in validation_feedback

    llm = get_fast_model()
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY")
    eval_author = EvalAuthor(
        experiment_dir=tmp_path,
        config=EvalAuthorConfig(),
        llm=llm,
    )
    insight = Insight(
        workspace="local",
        title="Harbor verifier contains invalid Python syntax",
        description=(
            "The shared check_tool_hallucination.py verifier contains a try statement without an except or finally "
            "clause. Repair every reported syntax error without changing the intended successful score of 1.0."
        ),
        agent="eval-author-repair-canary",
    )
    runner_conventions = (
        "This is a Harbor dataset. Verifier files live under each task's tests directory. "
        "Python verifier files are statically checked by await dataset.validate(); test.sh is checked as Bash. "
        "Preserve the existing verifier's intended behavior and repair every validation error."
    )

    summary = await asyncio.wait_for(
        eval_author.author_insight_metrics(
            insight,
            [],
            insight_suite,
            runner_conventions,
            validation_feedback=validation_feedback,
        ),
        timeout=300,
    )

    assert summary
    await insight_suite.validate()
    for verifier_path in (
        insight_suite_dir / "task-a" / "tests" / "check_tool_hallucination.py",
        insight_suite_dir / "task-b" / "tests" / "check_tool_hallucination.py",
    ):
        repaired_source = verifier_path.read_text(encoding="utf-8")
        assert "def check_tool_hallucination" in repaired_source
        assert "return 1.0" in repaired_source


@pytest.mark.skipif(
    not (_RUN_EVAL_AUTHOR_HARBOR_E2E and _HAS_EXPERIMENTALIST_LLM),
    reason=(
        "Set RUN_EVAL_AUTHOR_HARBOR_E2E=1 with EXPERIMENTALIST_API_BASE and EXPERIMENTALIST_API_KEY "
        "to run the live Harbor metric canary."
    ),
)
async def test_eval_author_metric_scores_known_failing_harbor_baseline_low(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An authored root-cause metric scores a known-failing Harbor baseline low."""
    insight_suite_dir = tmp_path / "insight-suite"
    agent_dir = tmp_path / "known-failing-agent"
    _write_known_failing_task(insight_suite_dir)
    _write_known_failing_agent(agent_dir)
    insight_suite = HarborDataset.from_path(insight_suite_dir)
    await insight_suite.validate()

    llm = get_fast_model()
    llm.config["temperature"] = 0.0
    monkeypatch.delenv("EXPERIMENTALIST_API_KEY")
    eval_author = EvalAuthor(
        experiment_dir=tmp_path,
        config=EvalAuthorConfig(),
        llm=llm,
    )
    eval_author.context.pop("trace_documentation", None)
    insight = Insight(
        workspace="local",
        title="Agent skips the required inventory lookup",
        description=(
            "The agent reports warehouse availability from memory instead of calling the required "
            "inventory_lookup tool. The metric must measure whether the current Harbor execution "
            "contains that required tool call, not whether the final answer happens to contain a quantity."
        ),
        agent="known-failing-baseline",
    )
    diagnostic = Diagnostic(
        outcome="FAILURE",
        summary=(
            "The execution trace contains only response generation. It has no tool span and no evidence "
            "that live inventory was retrieved before the answer."
        ),
        failure_point=1,
        root_cause="The agent answered from memory without calling the required inventory_lookup tool.",
    )
    runner_conventions = (
        "This is a Harbor dataset. Preserve the existing reward metric and add a new numeric root-cause metric. "
        "Verifier files live under each task's tests directory. After the agent runs, OTLP JSONL trace files are "
        "available under /logs/artifacts/traces. Every metric must be written as a numeric entry in "
        "/logs/verifier/reward.json, where higher is better and values are bounded to [0.0, 1.0]. Make the minimal "
        "verifier-only edit. Missing tool evidence is the expected failing case: it must score 0.0 while still "
        "writing reward.json and exiting successfully. Do not use an unguarded grep pipeline whose no-match status "
        "can abort a set -e script; prefer a small Python standard-library checker. Call await "
        "insight_suite.validate() once after editing, then return the metric summary as soon as validation passes; "
        "do not inspect unrelated files."
    )

    summary = await asyncio.wait_for(
        eval_author.author_insight_metrics(
            insight,
            [("known-failing-trace", diagnostic)],
            insight_suite,
            runner_conventions,
        ),
        timeout=600,
    )

    assert summary
    await insight_suite.validate()
    evaluator = HarborEvaluator(experiment_dir=tmp_path)
    result = await asyncio.wait_for(
        evaluator.run(
            agent=agent_dir,
            dataset=insight_suite,
            options=HarborEvaluatorConfig(
                force_rerun=True,
                job_name="known-failing-insight-metric",
                jobs_dir=Path("harbor-jobs"),
                n_concurrent_trials=1,
                quiet=True,
            ),
        ),
        timeout=600,
    )

    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.status == "completed", trial.error
    reward_ref = trial.resources["log:verifier/reward.json"]
    reward_path = local_path_from_uri(reward_ref.uri, context="Harbor verifier reward")
    reward_payload = json.loads(reward_path.read_text(encoding="utf-8"))
    assert reward_payload["reward"] == pytest.approx(1.0)

    insight_metric_names = set(reward_payload) - {"reward"}
    assert insight_metric_names
    insight_metric_values = {
        name: float(reward_payload[name])
        for name in insight_metric_names
        if isinstance(reward_payload[name], int | float) and not isinstance(reward_payload[name], bool)
    }
    assert set(insight_metric_values) == insight_metric_names
    assert all(0.0 <= value <= 1.0 for value in insight_metric_values.values())
    assert min(insight_metric_values.values()) <= 0.25
    assert insight_metric_names <= set(trial.metrics)
    print(
        json.dumps(
            {
                "authored_summary": summary,
                "reward_json": reward_payload,
            },
            sort_keys=True,
        )
    )
