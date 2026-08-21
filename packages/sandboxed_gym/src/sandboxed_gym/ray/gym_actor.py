# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ray actor that owns a :class:`SandboxedGymSession` (raw Gym results, no RL postprocess)."""

from __future__ import annotations

from typing import Any

import ray

from sandboxed_gym.orchestrator import SandboxedGymOrchestrator, SandboxedGymSession
from sandboxed_gym.serve_config import SandboxedGymServeConfig


GYM_ACTOR_FQN = "sandboxed_gym.ray.gym_actor.SandboxedGymActor"


@ray.remote(max_restarts=-1, max_task_retries=-1)
class SandboxedGymActor:
    """Trusted Ray proxy: broker + Gym host; returns raw ``/rollouts/run`` results."""

    def __init__(self, cfg: SandboxedGymServeConfig | dict[str, Any]) -> None:
        self._cfg = (
            cfg
            if isinstance(cfg, SandboxedGymServeConfig)
            else SandboxedGymServeConfig.model_validate(cfg)
        )
        self._session: SandboxedGymSession | None = None

    def spinup(self) -> dict[str, Any]:
        self._session = SandboxedGymOrchestrator().start(self._cfg)
        return self._session.descriptor().model_dump(mode="json")

    def run_rollouts(self, examples: list[dict[str, Any]]) -> list[Any]:
        if self._session is None:
            raise RuntimeError("SandboxedGymActor.spinup has not completed")
        return self._session.run_rollouts(examples)

    def shutdown(self) -> None:
        if self._session is not None:
            self._session.shutdown()
            self._session = None
