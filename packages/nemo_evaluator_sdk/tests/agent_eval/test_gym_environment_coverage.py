# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Coverage of the Gym runner across a representative sample of Gym environments.

The other Gym tests (``test_gym_runtime.py``, ``test_gym_aggregate_scores.py``) replay recorded
fixtures through the adapter and never invoke the CLI, so they encode whatever ``mcqa`` happens to do
and keep passing for every other environment. This module goes the other way: it drives the real
``gym`` CLI against several environments chosen to span Gym's dependency and wiring categories.

Gym ships 105 ``resources_servers`` — 68 with two or fewer dependencies, 28 with multi-dependency CPU
stacks, 6 heavy/GPU, and 10 requiring Docker — and ``mcqa`` is the easiest of all of them, so "the
runner works" has only ever been established for the least demanding case.

**Two layers, deliberately.** ``gym env validate`` merges configs, flags, and overrides and reports
unset ``???`` values, bad paths, and dangling cross-references *without Ray, servers, a model
endpoint, or credentials*. It is fast, offline, and answers most of what this sweep wants to know, so
every environment gets a validate test. Actually collecting rollouts additionally needs a reachable
model endpoint, so those tests skip unless one is configured.

That split matters because model wiring is not standardized. ``mcqa``/``gpqa_diamond``/
``wmt_translation`` reference a ``policy_model`` server fed by the global ``policy_base_url`` /
``policy_api_key`` / ``policy_model_name`` keys; ``gdpval`` wants a judge server named
``gdpval_judge_model`` that no shipped config defines; ``legal_agent_bench`` takes a raw
``judge_base_url``; and ``wmt_translation`` also loads a local COMET model that is not an endpoint at
all. Validate surfaces those differences as concrete errors instead of as a startup timeout.

Prerequisites, in the order the skips report them:

* **NeMo Gym installed in this environment** (``pip install nemo-gym``). Environments ship in the
  wheel, so no checkout is required.
* **The target environment's own dependencies** — each ``resources_server`` ships a
  ``requirements.txt``; install it from that directory so its ``-e nemo-gym[dev] @ ../../`` resolves.
* **Docker**, for environments whose agent works inside containers.
* **A model endpoint** (``NEMO_GYM_POLICY_BASE_URL`` and friends), for the rollout tests only.

Tracked by AALGO-485; the CI and GPU-runner story is AALGO-494.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from nemo_evaluator_sdk.agent_eval.evaluator import AgentEvaluator
from nemo_evaluator_sdk.agent_eval.runtimes.gym_runtime import (
    GymAgentTaskRunner,
    GymRuntimeConfig,
    _flatten_overrides,
    discover_gym_tasks,
)
from nemo_evaluator_sdk.agent_eval.tasks import AgentEvalRunConfig
from nemo_evaluator_sdk.agent_eval.trials import AgentEvalTrialStatus

pytestmark = [pytest.mark.integration, pytest.mark.slow]

#: Endpoint for the rollout tests. Gym itself reads credentials from a gitignored ``env.yaml`` in the
#: working directory; this only gates whether we attempt a run at all.
POLICY_BASE_URL_ENV = "NEMO_GYM_POLICY_BASE_URL"

_DEFAULT_AGENT = "simple_agent"
_DEFAULT_AGENT_CONFIG = "responses_api_agents/simple_agent/configs/simple_agent.yaml"

#: Keep runs small — this establishes that an environment works at all, not how well it scores.
_TASK_LIMIT = 2


@dataclass(frozen=True)
class GymEnvironmentCase:
    """One environment in the sample, with the prerequisites it adds beyond an installed Gym."""

    resources_server: str
    category: str
    #: Why this environment is in the sample rather than another from the same category.
    rationale: str
    needs_docker: bool = False
    needs_gpu: bool = False
    agent: str = _DEFAULT_AGENT
    agent_config: str = _DEFAULT_AGENT_CONFIG
    #: Mirrors ``GymRuntimeConfig.bind_resources_server``. False where the environment registers its
    #: resources-server under a name other than its own, so the caller must bind it explicitly.
    bind_resources_server: bool = True
    #: Nested config overrides this environment needs beyond the runner's automatic binding. Empty
    #: where the standard `policy_model` wiring is enough; populated as the sweep discovers what an
    #: environment actually requires.
    env_overrides: Mapping[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.resources_server}[{self.category}]"


CASES: tuple[GymEnvironmentCase, ...] = (
    GymEnvironmentCase(
        resources_server="mcqa",
        category="baseline",
        rationale=(
            "The environment every existing test is built on. Included so a failure elsewhere is "
            "attributable to that environment rather than to the runner or the local setup."
        ),
    ),
    GymEnvironmentCase(
        resources_server="gpqa_diamond",
        category="tiny",
        rationale=(
            "Control. Same multiple-choice shape as mcqa with comparably small dependencies, so a "
            "failure here means we encoded mcqa's specifics rather than the category's."
        ),
    ),
    GymEnvironmentCase(
        resources_server="gdpval",
        category="heavy-cpu-judge",
        rationale=(
            "Seven dependencies including binary wheels (PyMuPDF, pdfminer.six, python-docx), no "
            "GPU, and it ships a prompt config so it exercises the data-prep path mcqa skips. Also "
            "the clearest case of model wiring that is not standardized — see the overrides below."
        ),
        # Two Gym conventions this environment does not follow, both of which the caller has to know
        # about and neither of which is discoverable without reading its YAML or failing:
        #
        # 1. Its resources-server is registered as `gdpval_resources_server`, not `gdpval`. The
        #    runner's `bind_resources_server` binds the *environment* name (the simple_agent
        #    convention), so it must be disabled and bound by hand here.
        # 2. It references a judge model server named `gdpval_judge_model` that no shipped config
        #    defines — `responses_api_models/` provides model *types*, not this block — so the caller
        #    must construct it.
        #
        # We deliberately do not paper over either in the runner: they are Gym's inconsistencies, and
        # hiding them behind guesswork would make the runner wrong for environments that follow the
        # convention. Recorded here so the cost to a caller is visible.
        bind_resources_server=False,
        env_overrides={
            "simple_agent": {
                "responses_api_agents": {"simple_agent": {"resources_server": {"name": "gdpval_resources_server"}}}
            },
            "gdpval_judge_model": {
                "responses_api_models": {
                    "inference_provider": {
                        "entrypoint": "app.py",
                        # Interpolations, not literals: the judge shares the policy endpoint rather
                        # than needing a second one configured.
                        "base_url": "${policy_base_url}",
                        "api_key": "${policy_api_key}",
                        "model": "${policy_model_name}",
                    }
                }
            },
        },
    ),
    GymEnvironmentCase(
        resources_server="legal_agent_bench",
        category="docker",
        rationale=(
            "Harbor executes the task-local verifier inside Docker; needs a running daemon, ~10 GB "
            "of space, and a multi-minute first image build. Takes a raw `judge_base_url` rather "
            "than a model-server reference. Also runnable through the SDK's Harbor and Fabric "
            "examples, so it is the one environment comparable across three runners."
        ),
        needs_docker=True,
    ),
    GymEnvironmentCase(
        resources_server="wmt_translation",
        category="gpu",
        rationale=(
            "torch, torchvision, and unbabel-comet, plus a local COMET model (Unbabel/XCOMET-XXL) "
            "that is not an endpoint at all. Expected to fail without a GPU — the point of running "
            "it anyway is to check the failure is legible."
        ),
        needs_gpu=True,
    ),
)


def _gym_cli() -> str:
    """The `gym` CLI, or skip. Everything here needs it; nothing here needs a checkout."""
    resolved = shutil.which("gym")
    if resolved is None:
        pytest.skip("NeMo Gym is not installed in this environment (`pip install nemo-gym`)")
    return resolved


def _bounded_probe(argv: list[str]) -> bool:
    """True when the command exists and exits zero. Bounded: a wedged daemon must not stall the run."""
    if shutil.which(argv[0]) is None:
        return False
    try:
        return subprocess.run(argv, capture_output=True, timeout=10).returncode == 0
    except subprocess.TimeoutExpired:
        return False


def _environment_dir(gym: str, case: GymEnvironmentCase) -> Path:
    """Locate an environment's directory by asking the CLI, or skip.

    Deliberately not ``importlib.resources``: nemo-platform bans Ray by constraint
    (``"ray; sys_platform == 'never'"`` in the root pyproject, for an unfixed CVE) while Gym imports
    Ray at module load, so Gym cannot be installed in this SDK's environment. It lives in its own,
    reachable only through the ``gym`` binary on PATH — which means ``resources_servers.<name>`` is
    not importable here even when the environment is perfectly available.

    ``gym list resources-servers <name>`` reports the environment's config path and exits non-zero
    for one it cannot resolve, so it answers both questions across the venv boundary.
    """
    # `gym list` is a Hydra entry point too, so it also wants somewhere to put its run directory —
    # without this it drops an `outputs/<date>/<time>/` into whatever directory pytest ran from.
    with tempfile.TemporaryDirectory(prefix="gym-list-hydra-") as hydra_dir:
        proc = subprocess.run(
            [gym, "list", "resources-servers", case.resources_server, f"hydra.run.dir={hydra_dir}"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    if proc.returncode != 0:
        pytest.skip(
            f"Gym cannot resolve resources-server {case.resources_server!r}; install its own "
            "requirements.txt from the environment's directory (its `-e nemo-gym[dev] @ ../../` is "
            "relative to that directory, so it must be installed from there)"
        )
    config_line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("config:")), None)
    if config_line is None:
        pytest.skip(f"`gym list resources-servers {case.resources_server}` reported no config path to locate it by")
    # <env>/configs/<env>.yaml -> <env>
    return Path(config_line.removeprefix("config:").strip()).parent.parent


def _require_environment(gym: str, case: GymEnvironmentCase) -> Path:
    """Skip with one specific reason unless this case's prerequisites are present.

    The reasons are the deliverable: ``pytest -ra`` over this module is the coverage map, so each one
    names the single missing thing rather than a generic "prerequisites not met".
    """
    environment_dir = _environment_dir(gym, case)

    if case.needs_docker and not _bounded_probe(["docker", "info"]):
        pytest.skip(f"{case.resources_server} runs its verifier in Docker; no working daemon found")

    if case.needs_gpu and not _bounded_probe(["nvidia-smi"]):
        pytest.skip(f"{case.resources_server} scores with GPU models; no working nvidia-smi found")

    return environment_dir


def _selection(case: GymEnvironmentCase, hydra_dir: Path) -> list[str]:
    """The selection arguments the runner passes to both `gym env validate` and `gym env start`.

    ``hydra.run.dir`` mirrors what the runner does: Gym is a Hydra app and writes a timestamped run
    directory per invocation, defaulting to ``outputs/`` under the current directory. Left alone, a
    sweep drops one of those into the repo for every environment it checks.
    """
    argv = [
        "--config",
        case.agent_config,
        "--model-type",
        "inference_provider",
        "--resources-server",
        case.resources_server,
    ]
    if case.bind_resources_server:
        argv.append(f"+{case.agent}.responses_api_agents.{case.agent}.resources_server.name={case.resources_server}")
    argv.extend(_flatten_overrides(case.env_overrides))
    argv.append(f"hydra.run.dir={hydra_dir}")
    return argv


@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
def test_gym_environment_config_validates(case: GymEnvironmentCase, tmp_path: Path) -> None:
    """`gym env validate` accepts the config the runner would run.

    No Ray, no servers, no model endpoint, no credentials — so this runs anywhere Gym is installed
    and is where most of the sweep's signal comes from. A failure here is a concrete, readable
    report: an unset ``???``, a bad path, or a cross-reference to a server that is not defined.
    """
    gym = _gym_cli()
    # Only the environment itself is required. Docker and GPU are *execution* prerequisites, and
    # gating on them here would throw away the coverage this test exists for — `wmt_translation`'s
    # config would go unvalidated on every machine without an NVIDIA card, which is all of them
    # until AALGO-494 lands the GPU runner.
    _environment_dir(gym, case)

    proc = subprocess.run(
        [gym, "env", "validate", *_selection(case, tmp_path / "hydra")],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, (
        f"{case.resources_server}: `gym env validate` rejected the runner's config.\n{proc.stdout}\n{proc.stderr}"
    )


@pytest.mark.timeout(1800)
@pytest.mark.parametrize("case", CASES, ids=[case.id for case in CASES])
@pytest.mark.asyncio
async def test_gym_environment_runs_end_to_end(case: GymEnvironmentCase, tmp_path: Path) -> None:
    """Collect real rollouts and confirm the runner turns them into scored trials.

    Deliberately shallow: this establishes that a category works, not how well it scores. Reward
    values are Gym's own and are not asserted on — that would be testing Gym, not the runner.
    """
    gym = _gym_cli()
    environment_dir = _require_environment(gym, case)
    if not os.environ.get(POLICY_BASE_URL_ENV):
        pytest.skip(f"{POLICY_BASE_URL_ENV} is not set; rollout collection needs a reachable model endpoint")

    dataset = environment_dir / "data" / "example.jsonl"
    if not dataset.exists():
        pytest.skip(f"{case.resources_server} ships no data/example.jsonl at {dataset}")

    tasks = discover_gym_tasks(dataset)
    assert tasks, f"{case.resources_server}: discover_gym_tasks found no rows in {dataset}"
    tasks = tasks[:_TASK_LIMIT]

    runner = GymAgentTaskRunner(
        config=GymRuntimeConfig(
            agent=case.agent,
            agent_config=case.agent_config,
            resources_server=case.resources_server,
            num_repeats=1,
            bind_resources_server=case.bind_resources_server,
            env_overrides=dict(case.env_overrides),
        )
    )

    result = await AgentEvaluator().run(
        tasks=tasks,
        target=runner,
        config=AgentEvalRunConfig(work_dir=tmp_path / "gym_run", parallelism=1),
    )

    assert result.summary.task_count == len(tasks)
    assert len(result.trials) == len(tasks)

    failed = [trial for trial in result.trials if trial.status is not AgentEvalTrialStatus.COMPLETED]
    assert not failed, f"{case.resources_server}: trials did not complete: {[(t.task_id, t.status) for t in failed]}"

    assert runner.runner_info().name == "gym"
    assert result.scores, f"{case.resources_server}: no metric scores were produced"
