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

"""In-memory episode backend for development and tests.

Provisions nothing and isolates nothing. It exists so the broker, the NeMo-Gym client, and the
``SandboxedGymActor`` handshake can be exercised without a cluster. Selecting it requires two
independent config keys so it cannot be reached by a single typo.
"""

import logging
from dataclasses import dataclass, field

from nemo_gym.sandbox.providers.base import SandboxExecResult, SandboxStatus

from sandboxed_gym.backends.base import (
    EpisodeBackendError,
    SanitizedEpisodeSpec,
)
from sandboxed_gym.egress import EgressPolicy


LOGGER = logging.getLogger(__name__)


@dataclass
class _MemoryEpisode:
    spec: SanitizedEpisodeSpec
    files: dict[str, bytes] = field(default_factory=dict)


class InMemoryEpisodeBackend:
    """Episode backend that records requests instead of provisioning sandboxes."""

    name = "memory"

    def __init__(self, egress: EgressPolicy) -> None:
        LOGGER.warning(
            "Episode broker is using the in-memory backend. No episode sandbox is created and no "
            "isolation is applied. This backend is for development and tests only."
        )
        # Recorded so audit output reads the same as any other backend. Nothing enforces it here;
        # that is the point of the two-key opt-in that selects this backend.
        self.egress = egress
        self._episodes: dict[str, _MemoryEpisode] = {}
        self._counter = 0

    def _require(self, backend_id: str) -> _MemoryEpisode:
        episode = self._episodes.get(backend_id)
        if episode is None:
            raise EpisodeBackendError(f"unknown episode {backend_id!r}")
        return episode

    async def create(self, spec: SanitizedEpisodeSpec) -> str:
        """Record the spec and return a synthetic backend id."""
        self._counter += 1
        backend_id = f"mem-{self._counter}"
        self._episodes[backend_id] = _MemoryEpisode(spec=spec)
        return backend_id

    async def status(self, backend_id: str) -> SandboxStatus:
        """Return ``RUNNING`` for a known episode."""
        self._require(backend_id)
        return SandboxStatus.RUNNING

    async def exec(
        self,
        backend_id: str,
        command: str,
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_s: float | None = None,
        user: str | int | None = None,
    ) -> SandboxExecResult:
        """Echo the command back instead of running it."""
        self._require(backend_id)
        return SandboxExecResult(
            stdout=f"memory-backend ran: {command}", stderr=None, return_code=0
        )

    async def upload_file(self, backend_id: str, path: str, content: bytes) -> None:
        """Store file content in memory."""
        self._require(backend_id).files[path] = content

    async def download_file(self, backend_id: str, path: str) -> bytes:
        """Return previously stored file content."""
        episode = self._require(backend_id)
        if path not in episode.files:
            raise EpisodeBackendError(f"no such file in episode {backend_id!r}: {path}")
        return episode.files[path]

    async def close(self, backend_id: str) -> None:
        """Drop the episode. Idempotent."""
        self._episodes.pop(backend_id, None)

    async def list_backend_ids(self, job_id: str) -> list[str]:
        """List recorded episodes belonging to ``job_id``."""
        return [
            backend_id
            for backend_id, episode in self._episodes.items()
            if episode.spec.job_id == job_id
        ]

    async def aclose(self) -> None:
        """Drop all recorded episodes."""
        self._episodes.clear()
