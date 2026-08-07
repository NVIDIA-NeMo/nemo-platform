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

"""Ownership and concurrency bookkeeping for live episodes."""

import asyncio
import secrets

from nemo_gym.sandbox.broker import BrokerErrorCode

from sandboxed_gym.errors import BrokerRequestError


class EpisodeRegistry:
    """Maps broker-owned opaque handles to backend ids, and caps how many exist at once.

    Handles are opaque on purpose: the untrusted caller never learns a backend-native sandbox id,
    so a leaked handle is useless against any backend API, and every route resolves through this
    map rather than trusting an id off the wire.
    """

    def __init__(self, *, max_concurrent: int) -> None:
        self._max_concurrent = max_concurrent
        self._lock = asyncio.Lock()
        # ``None`` marks a reserved-but-not-yet-created episode; it holds a concurrency slot but
        # cannot be resolved by any route.
        self._backend_ids: dict[str, str | None] = {}

    async def reserve(self) -> str:
        """Claim a concurrency slot and return a new opaque episode id.

        Raises:
            BrokerRequestError: If the job already holds the maximum number of episodes.
        """
        async with self._lock:
            if len(self._backend_ids) >= self._max_concurrent:
                raise BrokerRequestError(
                    BrokerErrorCode.QUOTA_EXCEEDED,
                    f"job already holds the maximum of {self._max_concurrent} concurrent episodes",
                    status_code=429,
                )
            episode_id = f"ep_{secrets.token_urlsafe(16)}"
            self._backend_ids[episode_id] = None
            return episode_id

    async def bind(self, episode_id: str, backend_id: str) -> None:
        """Attach a created backend id to a reserved episode id."""
        async with self._lock:
            self._backend_ids[episode_id] = backend_id

    async def release(self, episode_id: str) -> str | None:
        """Drop an episode and free its slot, returning its backend id if it had one."""
        async with self._lock:
            return self._backend_ids.pop(episode_id, None)

    async def resolve(self, episode_id: str) -> str:
        """Return the backend id for an episode this broker owns.

        Raises:
            BrokerRequestError: If the handle is unknown or not yet created.
        """
        async with self._lock:
            backend_id = self._backend_ids.get(episode_id)
        if backend_id is None:
            raise BrokerRequestError(
                BrokerErrorCode.EPISODE_NOT_FOUND,
                f"unknown episode: {episode_id}",
                status_code=404,
            )
        return backend_id

    async def drain(self) -> list[str]:
        """Empty the registry and return every backend id it held, for teardown."""
        async with self._lock:
            backend_ids = [
                backend_id
                for backend_id in self._backend_ids.values()
                if backend_id is not None
            ]
            self._backend_ids.clear()
            return backend_ids

    async def size(self) -> int:
        """Return how many episodes currently hold a slot."""
        async with self._lock:
            return len(self._backend_ids)
