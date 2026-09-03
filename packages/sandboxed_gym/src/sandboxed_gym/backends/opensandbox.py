# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""OpenSandbox episode backend.

Delegates to NeMo-Gym's ``OpenSandboxProvider`` rather than reimplementing it: the retry
classification, readiness probing, reconnect-after-create polling, and non-root exec handling
there are load-bearing and stay single-sourced. What this module owns is the part that has to be
trusted -- building the create request field by field from an already-sanitized spec, so nothing a
caller supplied can ride along, and establishing the egress policy at the only moment OpenSandbox
allows it.
"""

import logging
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from sandboxed_gym.backends._opensandbox_driver import OpenSandboxDriver, connection_config
from sandboxed_gym.backends.archive import (
    download_dir_via_archive,
    upload_dir_via_archive,
)
from sandboxed_gym.backends.base import (
    EpisodeBackendError,
    SanitizedEpisodeSpec,
    UnsupportedEpisodeOperationError,
)
from sandboxed_gym.egress import EgressPolicy
from sandboxed_gym.opensandbox_policy import (
    canonical_egress_target,
    create_options_with_policy,
)
from sandboxed_gym.sandbox_types import (
    SandboxExecResult,
    SandboxHandle,
    SandboxResources,
    SandboxSpec,
    SandboxStatus,
)

LOGGER = logging.getLogger(__name__)


class OpenSandboxEpisodeBackend:
    """Episode backend backed by OpenSandbox, driven through its own SDK.

    Holds the OpenSandbox credential. It lives only in this trusted process and is never passed to
    the job sandbox.
    """

    name = "opensandbox"

    def __init__(
        self,
        *,
        egress: EgressPolicy,
        connection: Mapping[str, Any] | None = None,
        create: Mapping[str, Any] | None = None,
        probe: Mapping[str, Any] | None = None,
        operations: Mapping[str, Any] | None = None,
        verification: Literal["off", "default_action", "strict"] = "default_action",
    ) -> None:
        self.egress = egress
        self._verification = verification
        self._connection = dict(connection) if connection else {}
        self._provider = OpenSandboxDriver(
            connection=self._connection,
            create=create_options_with_policy(create, egress),
            probe=probe,
            operations=operations,
        )
        self._handles: dict[str, SandboxHandle] = {}

    def _sdk_connection_config(self) -> Any:
        """The SDK connection config for calls this backend makes outside the driver.

        Listing sandboxes goes through the SDK's manager, which the driver does not wrap. Built
        from the same mapping and the same helper, so the two cannot drift.
        """
        return connection_config(self._connection)

    def _require(self, backend_id: str) -> SandboxHandle:
        handle = self._handles.get(backend_id)
        if handle is None:
            raise EpisodeBackendError(f"unknown episode {backend_id!r}")
        return handle

    def _to_sandbox_spec(self, spec: SanitizedEpisodeSpec) -> SandboxSpec:
        """Build the provider spec explicitly, field by field.

        Nothing is spread from a caller-supplied mapping. ``provider_options`` is never populated,
        which is what keeps volumes, platform, snapshot references, and the ``extensions``
        privilege lever unreachable no matter what the request contained.
        """
        if spec.mounts:
            raise UnsupportedEpisodeOperationError(
                "this backend does not mount volumes into episodes; content is staged as files"
            )
        resources = spec.resources
        return SandboxSpec(
            image=spec.image,
            ttl_s=spec.ttl_s,
            ready_timeout_s=spec.ready_timeout_s,
            workdir=spec.workdir,
            env=dict(spec.env),
            metadata=dict(spec.metadata),
            resources=SandboxResources(
                cpu=resources.cpu,
                memory_mib=resources.memory_mib,
                disk_gib=resources.disk_gib,
                gpu=resources.gpu,
                gpu_type=resources.gpu_type,
            ),
            entrypoint=list(spec.entrypoint) if spec.entrypoint is not None else None,
        )

    async def _assert_egress_applied(self, handle: SandboxHandle) -> None:
        """Confirm the egress policy we asked for is the one in force.

        Setting the policy is enforcement by construction; this is enforcement by verification, so
        a server that ignored the policy, or a deployment whose sidecar is not wired up, surfaces
        as a failed episode rather than as an episode with quietly unrestricted network access.

        ``default_action`` is always fatal when it disagrees: it is unambiguous, it decides what
        happens to everything no rule matches, and create is the only moment it can be set. Missing
        *rules* are only fatal under ``strict``, because the sidecar returns a merged, re-serialized
        policy and a textual difference there is more likely to mean reformatting than a real gap.
        Failing every episode closed over that would be worse than reporting it.
        """
        if self._verification == "off":
            return
        get_policy = getattr(handle.raw, "get_egress_policy", None)
        if get_policy is None:
            LOGGER.warning(
                "OpenSandbox handle for episode %s cannot report its egress policy; skipping verification",
                handle.sandbox_id,
            )
            return

        applied = await get_policy()
        applied_default = getattr(applied, "default_action", None)
        if applied_default != self.egress.default_action:
            raise EpisodeBackendError(
                f"episode {handle.sandbox_id} applied egress default_action="
                f"{applied_default!r}, expected {self.egress.default_action!r}"
            )

        applied_targets = {
            (
                getattr(rule, "action", None),
                canonical_egress_target(str(getattr(rule, "target", ""))),
            )
            for rule in (getattr(applied, "egress", None) or ())
        }
        missing = sorted(
            (rule.action, rule.target)
            for rule in self.egress.rules
            if (rule.action, canonical_egress_target(rule.target)) not in applied_targets
        )
        if not missing:
            return

        if self._verification == "strict":
            raise EpisodeBackendError(
                f"episode {handle.sandbox_id} did not apply {len(missing)} requested egress "
                f"rule(s); first few: {missing[:5]}"
            )
        LOGGER.warning(
            "Episode %s did not report %d requested egress rule(s) (first few: %s). The default "
            "action matched, so this may be the sidecar re-serializing a merged policy rather "
            "than a real gap. Set egress_verification='strict' once a deployment is known to "
            "round-trip rules cleanly.",
            handle.sandbox_id,
            len(missing),
            missing[:5],
        )

    async def create(self, spec: SanitizedEpisodeSpec) -> str:
        """Create one episode sandbox and confirm its egress policy took effect."""
        handle = await self._provider.create(self._to_sandbox_spec(spec))
        self._handles[handle.sandbox_id] = handle
        try:
            await self._assert_egress_applied(handle)
        except BaseException:
            await self.close(handle.sandbox_id)
            raise
        return handle.sandbox_id

    async def status(self, backend_id: str) -> SandboxStatus:
        """Return the episode's lifecycle status."""
        return await self._provider.status(self._require(backend_id))

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
        """Run one command inside the episode."""
        return await self._provider.exec(
            self._require(backend_id),
            command,
            cwd=cwd,
            env=env,
            timeout_s=timeout_s,
            user=user,
        )

    async def upload_file(self, backend_id: str, path: str, content: bytes) -> None:
        """Write one file into the episode.

        Staged through a temporary file because the provider's file API is path-based, the same
        way NeMo-Gym's own sandbox API stages ``SandboxSpec.files``. Going through the public
        surface keeps this off the provider's private helpers.
        """
        handle = self._require(backend_id)
        with tempfile.TemporaryDirectory(prefix="nemo-rl-episode-upload-") as tmp_dir:
            source = Path(tmp_dir) / "payload"
            source.write_bytes(content)
            await self._provider.upload_file(handle, source, path)

    async def download_file(self, backend_id: str, path: str) -> bytes:
        """Read one file out of the episode."""
        handle = self._require(backend_id)
        with tempfile.TemporaryDirectory(prefix="nemo-rl-episode-download-") as tmp_dir:
            target = Path(tmp_dir) / "payload"
            await self._provider.download_file(handle, path, target)
            return target.read_bytes()

    async def upload_dir(self, backend_id: str, path: str, archive: bytes) -> None:
        """Unpack a gzipped tar into the episode.

        Delegates to the shared archive helpers: the OpenSandbox provider's file API is one file at
        a time, so there is no native directory transport here to prefer over them.
        """
        await upload_dir_via_archive(self, backend_id, path, archive)

    async def download_dir(self, backend_id: str, path: str) -> bytes:
        """Return the episode directory as a gzipped tar."""
        return await download_dir_via_archive(self, backend_id, path)

    async def list_backend_ids(self, job_id: str) -> list[str]:
        """List episodes OpenSandbox believes belong to ``job_id``.

        Queries by the job-id metadata the broker stamps, which OpenSandbox turns into a pod label,
        so this sees episodes this process did not create -- the case that matters when
        reconciling orphans.
        """
        from opensandbox.manager import SandboxManager
        from opensandbox.models.sandboxes import SandboxFilter

        from sandboxed_gym.config import JOB_ID_METADATA_KEY

        manager = await SandboxManager.create(connection_config=self._sdk_connection_config())
        try:
            backend_ids: list[str] = []
            page = 1
            while True:
                result = await manager.list_sandbox_infos(
                    SandboxFilter(metadata={JOB_ID_METADATA_KEY: job_id}, page=page)
                )
                backend_ids.extend(info.id for info in result.sandbox_infos)
                if not result.pagination.has_next_page:
                    return backend_ids
                page += 1
        finally:
            await manager.close()

    async def close(self, backend_id: str) -> None:
        """Terminate the episode. Idempotent."""
        handle = self._handles.pop(backend_id, None)
        if handle is None:
            return
        await self._provider.close(handle)

    async def aclose(self) -> None:
        """Release provider-scoped resources."""
        await self._provider.aclose()
