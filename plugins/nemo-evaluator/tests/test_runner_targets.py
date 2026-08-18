# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Describing a live runner as the target spec that reproduces it as a job."""

from __future__ import annotations

import pytest
from nemo_evaluator.jobs.agent_spec import GymRunnerTarget
from nemo_evaluator.jobs.runner_targets import UnsubmittableRunnerError, runner_to_target
from nemo_evaluator_sdk.agent_eval.runtimes.gym import GymAgentTaskRunner, GymRuntimeConfig


def _configured() -> GymRuntimeConfig:
    """A config with every field set away from its default.

    Defaults would let a dropped field pass by coincidence — the target would carry the same value
    the runner had, for the wrong reason.
    """
    return GymRuntimeConfig(
        agent="simple_agent",
        agent_config="responses_api_agents/simple_agent/configs/simple_agent.yaml",
        resources_server="gdpval",
        model_type="openai_model",
        bind_resources_server=False,
        hydra_params={"simple_agent": {"responses_api_agents": {"x": 1}}},
        env_vars={"WMT_TRANSLATION_COMET_PY_CACHE": "/shared/cache"},
        num_repeats=3,
        concurrency=7,
        startup_timeout_s=1800.0,
        collection_timeout_s=3600.0,
        shutdown_grace_s=45.0,
        reward_key="score",
    )


def test_a_gym_runner_describes_itself_as_a_submittable_target() -> None:
    # The point of the conversion: an evaluation someone got working locally becomes a job spec
    # without retyping its configuration — which is where the subtle divergences come from.
    config = _configured()

    target = runner_to_target(GymAgentTaskRunner(config=config))

    assert isinstance(target, GymRunnerTarget)
    assert target.kind == "gym"
    # Every field arrives, unchanged. `kind` is the only addition — it discriminates the union and
    # has no runtime counterpart.
    assert target.model_dump(exclude={"kind"}) == config.model_dump()


def test_every_field_actually_travels_rather_than_defaulting() -> None:
    # Guards the failure this conversion exists to prevent: a field silently dropped, so the
    # submitted job runs something different from what was tested. Asserting values differ from
    # their defaults is what makes the round-trip above meaningful.
    config = _configured()
    defaults = {
        name: field.get_default(call_default_factory=True) for name, field in GymRuntimeConfig.model_fields.items()
    }
    carried = runner_to_target(GymAgentTaskRunner(config=config)).model_dump(exclude={"kind"})

    indistinguishable = [name for name, value in carried.items() if value == defaults.get(name)]
    assert not indistinguishable, (
        f"these fields match their defaults, so carrying them is untested: {indistinguishable}"
    )


def test_the_config_read_back_is_the_one_the_runner_holds() -> None:
    # The conversion reads `runner.config`, not `runner_info()`, because the latter redacts
    # credential-shaped values — rebuilding from it would submit `<redacted>` as a real setting.
    config = GymRuntimeConfig(
        agent="a",
        agent_config="c",
        resources_server="r",
        env_vars={"OPENAI_API_KEY": "sk-real-value", "HTTPS_PROXY": "http://proxy:8080"},
    )
    runner = GymAgentTaskRunner(config=config)

    target = runner_to_target(runner)

    assert runner.runner_info().config["env_vars"]["OPENAI_API_KEY"] == "<redacted>"
    assert isinstance(target, GymRunnerTarget)
    assert target.env_vars["OPENAI_API_KEY"] == "sk-real-value"


def test_an_unsupported_runner_is_refused_by_name() -> None:
    # Only Gym has a target today. A runner with no wire form must say so rather than produce a
    # spec that silently runs something else.
    class _Unsupported:
        def runner_info(self):  # pragma: no cover - never reached
            raise NotImplementedError

        async def run_tasks(self, tasks, config=None):  # pragma: no cover - never reached
            return []

    with pytest.raises(UnsubmittableRunnerError) as excinfo:
        runner_to_target(_Unsupported())

    message = str(excinfo.value)
    assert "_Unsupported" in message, "the message must name the runner that could not be converted"
    # Points at the alternative rather than dead-ending.
    assert "AgentEvaluator()" in message
