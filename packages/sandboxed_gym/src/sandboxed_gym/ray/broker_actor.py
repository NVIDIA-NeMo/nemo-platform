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

"""Ray actor wrapping :class:`sandboxed_gym.broker.EpisodeBrokerServer`."""

from __future__ import annotations

from typing import Any

import ray

from sandboxed_gym.broker import EpisodeBrokerServer
from sandboxed_gym.config import BrokerEndpoint, EpisodeBrokerConfig


BROKER_ACTOR_FQN = "sandboxed_gym.ray.broker_actor.SandboxEpisodeBrokerActor"


# Deliberately no max_restarts: a silently restarted broker would lose the handle map.
@ray.remote
class SandboxEpisodeBrokerActor:
    """Ray placement wrapper around the in-process episode broker server."""

    def __init__(self, config: EpisodeBrokerConfig | dict[str, Any]) -> None:
        self._server = EpisodeBrokerServer(config)

    def start(self) -> BrokerEndpoint:
        return self._server.start()

    def get_endpoint(self) -> BrokerEndpoint:
        return self._server.get_endpoint()

    def shutdown(self) -> None:
        self._server.shutdown()


def start_episode_broker(
    config: EpisodeBrokerConfig | dict[str, Any],
    *,
    node_id: str | None = None,
    extra_ray_options: dict[str, Any] | None = None,
) -> tuple[Any, BrokerEndpoint]:
    """Create and start the broker Ray actor; return ``(handle, endpoint)``."""
    from ray.util.scheduling_strategies import NodeAffinitySchedulingStrategy

    options: dict[str, Any] = {}
    if node_id is not None:
        options["scheduling_strategy"] = NodeAffinitySchedulingStrategy(
            node_id=node_id, soft=False
        )
    if extra_ray_options:
        options.update(extra_ray_options)

    actor = SandboxEpisodeBrokerActor.options(**options).remote(config)
    endpoint = ray.get(actor.start.remote())
    return actor, endpoint
