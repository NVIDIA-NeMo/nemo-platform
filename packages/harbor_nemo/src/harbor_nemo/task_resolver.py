# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Resolving ``org/name@ref`` to an archive on the NeMo platform."""

from __future__ import annotations

import re
from typing import Any, override

from harbor.models.registry import ResolvedTaskVersion
from harbor.registry.task_resolver import BaseTaskResolver

from harbor_nemo.client import NemoClient, NotFound
from harbor_nemo.config import NemoConfig
from harbor_nemo.names import NameMappingError, to_entity_name

#: Harbor writes a pinned reference as ``sha256:<hex>`` (see ``PackageTaskId.ref``).
_SHA256_PREFIX = "sha256:"
_HEX_DIGEST = re.compile(r"^[0-9a-f]{64}$")

#: How many revisions to walk when resolving a Harbor content hash. Generous: the answer is
#: almost always the head or one of the last few revisions, and the alternative to a bound is
#: an unbounded scan of a task republished thousands of times.
_MAX_REVISION_SCAN = 200


class NemoTaskResolver(BaseTaskResolver):
    """Resolves Harbor task references against NeMo's stored tasks.

    **Two digests are in play and they are not interchangeable.** NeMo addresses a revision by
    a digest of the revision's *content* (canonical JSON of the stored spec). Harbor addresses
    a version by a digest of the task *directory's files*, which NeMo stores as a field,
    ``spec.archive_digest``. A ``sha256:`` reference arriving here is always Harbor's, and
    passing it to NeMo's revision selector returns 404 — verified against a live platform.
    So a content-pinned lookup is a scan over revisions comparing ``archive_digest``, not a
    direct fetch.

    ``record_download`` is deliberately left as the inherited no-op. The platform has no
    counter primitive, so implementing it would mean a read-modify-write against the single
    hottest entity per package on every download — a poor trade for best-effort telemetry.
    """

    def __init__(self, client: NemoClient, config: NemoConfig) -> None:
        self._client = client
        self._config = config

    def _task_url(self, entity_name: str) -> str:
        return f"{self._config.tasks_url}/{entity_name}"

    @staticmethod
    def _to_resolved(entity_name: str, workspace: str, task: dict[str, Any]) -> ResolvedTaskVersion:
        spec = task.get("spec") or {}
        if spec.get("kind") != "harbor":
            # An agent-eval task stored under a name Harbor asked for. Not a Harbor package,
            # so from Harbor's point of view it does not exist — and saying so as ValueError
            # keeps `package_type` able to fall through to the dataset probe.
            raise ValueError(
                f"Task {workspace}/{entity_name} is a {spec.get('kind')!r} task, not a Harbor package."
            )
        revision = task.get("revision")
        return ResolvedTaskVersion(
            id=f"{workspace}/{entity_name}#{revision}",
            archive_path=spec["archive_ref"],
            content_hash=spec["archive_digest"],
            revision=revision,
        )

    async def _revisions(self, entity_name: str) -> list[dict[str, Any]]:
        """The task's revisions, newest first.

        Sorted here rather than trusting a query parameter: the ordering this scan depends on
        is worth owning, and the listing is already bounded by ``page_size``.
        """
        listing = await self._client.get_json(
            f"{self._task_url(entity_name)}/revisions",
            params={"page_size": _MAX_REVISION_SCAN},
        )
        entries = listing.get("data", [])
        return sorted(entries, key=lambda entry: entry.get("revision", 0), reverse=True)

    async def _resolve_by_archive_digest(
        self, entity_name: str, digest: str
    ) -> ResolvedTaskVersion:
        """Find the revision whose task directory hashed to ``digest``.

        Checks the head first — republishing the same content is the common case, so the
        current revision is the likely answer and costs one request.
        """
        head = await self._client.get_json(self._task_url(entity_name))
        if (head.get("spec") or {}).get("archive_digest") == digest:
            return self._to_resolved(entity_name, self._config.workspace, head)

        entries = await self._revisions(entity_name)
        for entry in entries:
            # Fetch by the revision's *content hash*, never its ordinal. The platform reads a
            # non-digest fragment as a tag name, so `/revisions/2` is a lookup for a tag called
            # "2" and 404s — which surfaced as a bogus "task version not found" for any
            # digest-pinned download that was not the head.
            revision = await self._client.get_json(
                f"{self._task_url(entity_name)}/revisions/{entry['content_hash']}"
            )
            if (revision.get("spec") or {}).get("archive_digest") == digest:
                return self._to_resolved(entity_name, self._config.workspace, revision)

        scanned = len(entries)
        hint = (
            f" (scanned the most recent {scanned}; a match older than that would not be found)"
            if scanned >= _MAX_REVISION_SCAN
            else ""
        )
        raise ValueError(f"No revision of {entity_name} has content hash {digest}{hint}")

    async def revision_digest_for_archive(self, org: str, name: str, archive_digest: str) -> str:
        """The NeMo *revision* digest of the revision whose archive hashed to ``archive_digest``.

        Exists to pin a taskset member. A Harbor manifest pins a task by the archive digest,
        while a taskset pins by NeMo's revision digest, so publishing a dataset with its pins
        intact means translating between the two hash spaces — one lookup per member, which is
        why an unpinned member ref is the cheaper (and lossier) alternative.
        """
        entity_name = to_entity_name(org, name)
        digest = (
            archive_digest[len(_SHA256_PREFIX) :]
            if archive_digest.startswith(_SHA256_PREFIX)
            else archive_digest
        )
        entries = await self._revisions(entity_name)
        by_ordinal = {entry.get("revision"): entry.get("content_hash", "") for entry in entries}

        head = await self._client.get_json(self._task_url(entity_name))
        if (head.get("spec") or {}).get("archive_digest") == digest:
            current = by_ordinal.get(head.get("revision"))
            if current:
                return current

        for entry in entries:
            revision = await self._client.get_json(
                f"{self._task_url(entity_name)}/revisions/{entry['content_hash']}"
            )
            if (revision.get("spec") or {}).get("archive_digest") == digest:
                return entry["content_hash"]

        raise ValueError(f"No revision of {org}/{name} has content hash {digest}")

    @override
    async def resolve_version(
        self, org: str, name: str, ref: str = "latest"
    ) -> ResolvedTaskVersion:
        # A reference NeMo could never have stored is a reference NeMo does not have.
        # NameMappingError is a ValueError, so this already reads as "not found".
        entity_name = to_entity_name(org, name)

        selector = ref[len(_SHA256_PREFIX) :] if ref.startswith(_SHA256_PREFIX) else ref
        try:
            if ref.startswith(_SHA256_PREFIX) and _HEX_DIGEST.match(selector):
                return await self._resolve_by_archive_digest(entity_name, selector)

            if selector.isdigit():
                # Harbor's `ref` may be a revision ordinal, but the platform reads any
                # non-digest fragment as a *tag*, so asking for `/revisions/2` looks for a tag
                # named "2". Translate the ordinal to that revision's content hash first.
                ordinal = int(selector)
                for entry in await self._revisions(entity_name):
                    if entry.get("revision") == ordinal:
                        selector = entry["content_hash"]
                        break
                else:
                    raise ValueError(
                        f"Task version not found: {org}/{name}@{ref} "
                        f"(no revision {ordinal})"
                    )

            # A tag, or a NeMo revision digest — both of which the platform's own revision
            # selector understands directly.
            task = await self._client.get_json(
                f"{self._task_url(entity_name)}/revisions/{selector}"
            )
            return self._to_resolved(entity_name, self._config.workspace, task)
        except NotFound as exc:
            # The load-bearing translation. `BaseRegistryBackend.package_type` catches exactly
            # ValueError to tell "absent" from "broken"; auth and transport failures are
            # already separate exception types by the time they reach here, so they propagate.
            raise ValueError(f"Task version not found: {org}/{name}@{ref}") from exc


__all__ = ["NemoTaskResolver", "NameMappingError"]
