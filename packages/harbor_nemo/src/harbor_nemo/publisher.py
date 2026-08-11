# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The publish path: Harbor packages into NeMo tasks and tasksets."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, override

from harbor.constants import ARCHIVE_FILENAME
from harbor.models.dataset.manifest import DatasetManifest
from harbor.models.dataset.paths import DatasetPaths
from harbor.models.task.config import TaskConfig
from harbor.models.task.paths import TaskPaths
from harbor.models.task.task import Task
from harbor.publisher.base import BasePublisher
from harbor.publisher.errors import PublishBackendError
from harbor.publisher.packager import Packager
from harbor.publisher.results import (
    DatasetPublishResult,
    FilePublishResult,
    PublishResult,
)

from harbor_nemo.client import NemoClient, NotFound
from harbor_nemo.config import NemoConfig
from harbor_nemo.names import NameMappingError, to_entity_name
from harbor_nemo.storage import NemoStorage
from harbor_nemo.task_resolver import NemoTaskResolver

LATEST_TAG = "latest"

#: Metadata key under which a dataset's dataset-level files are recorded. A taskset has no
#: field for them, so they ride as a JSON string here. This is the stopgap: the durable fix is
#: a file-reference field on the taskset entity, at which point this key becomes legacy.
DATASET_FILES_METADATA_KEY = "harbor.files"

#: Harbor's package name (``org/short-name``) as published, kept alongside the folded entity
#: name so the original reference survives the mapping and can be shown back to users.
PACKAGE_NAME_METADATA_KEY = "harbor.package_name"

#: Harbor's ``visibility``. NeMo has no per-entity visibility — access is a workspace-level
#: question — so recording it keeps the publisher's argument from being silently discarded,
#: but it is documentation, not enforcement.
VISIBILITY_METADATA_KEY = "harbor.visibility"


def _metadata(items: dict[str, str]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in items.items()]


class NemoPublisher(BasePublisher):
    """Publishes Harbor packages to a NeMo platform.

    Storage is injected rather than constructed here: the archive path recorded on a task is a
    literal path issued by one fileset, so the publisher must write blobs to the same place
    the backend's resolver will later read them from.

    ``_create_archive`` and ``remote_path`` are inherited untouched, which is what keeps an
    archive a pure function of file contents — a package published here is byte-identical to
    the same package on the public Hub, so a content hash computed against one is still valid
    against the other.
    """

    def __init__(
        self,
        client: NemoClient,
        config: NemoConfig,
        storage: NemoStorage,
        resolver: "NemoTaskResolver",
    ) -> None:
        self._client = client
        self._config = config
        self.storage = storage
        # Publishing a dataset means resolving its members' pins, so the publisher needs the
        # same resolver the download side uses — not a second one that could point elsewhere.
        self._resolver = resolver

    def _task_url(self, entity_name: str) -> str:
        return f"{self._config.tasks_url}/{entity_name}"

    def _taskset_url(self, entity_name: str) -> str:
        return f"{self._config.tasksets_url}/{entity_name}"

    @override
    async def check_auth(self) -> None:
        """Confirm the platform is reachable and the caller may read the workspace.

        Any 401/403 is already a ``PublishAuthError``/``PublishPermissionError`` by the time
        the client returns, so this only has to make a cheap authenticated request and let a
        missing workspace surface as a backend error rather than an auth one.
        """
        try:
            await self._client.get_json(self._config.tasks_url, params={"page_size": 1})
        except NotFound as exc:
            raise PublishBackendError(
                f"Workspace {self._config.workspace!r} does not exist on "
                f"{self._config.base_url}."
            ) from exc

    async def _get_task(self, entity_name: str) -> dict[str, Any] | None:
        try:
            return await self._client.get_json(self._task_url(entity_name))
        except NotFound:
            return None

    @override
    async def publish_file(self, package_name: str, file_path: Path) -> FilePublishResult:
        content_hash = Packager.compute_file_hash(file_path)
        remote_path = self.remote_path(package_name, content_hash, file_path.name)
        file_size = file_path.stat().st_size

        upload_start = time.monotonic()
        # Check-then-act: two concurrent publishes of identical content can both miss here and
        # both upload. That is safe *because* the path is content addressed — they write
        # byte-identical bytes to the same key — but it does mean `skipped` is a report of
        # what this call observed, not a distributed lock.
        skipped = await self.storage.exists(remote_path)
        if not skipped:
            await self.storage.upload_file(file_path, remote_path)
        upload_time = time.monotonic() - upload_start

        return FilePublishResult(
            content_hash=content_hash,
            # The self-describing reference, not the bare path: this becomes
            # `DatasetFileInfo.storage_path` and is later handed back to `download_file`.
            remote_path=self.storage.to_fileset_ref(remote_path),
            file_size_bytes=file_size,
            upload_time_sec=round(upload_time, 3),
            skipped=skipped,
        )

    async def _put_task(self, entity_name: str, body: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Publish a revision. Returns ``(task, created)``.

        The platform answers 201 when it cut a new revision and 200 when the content was
        already published — that status code is the only place the distinction appears, and it
        is exactly Harbor's ``skipped``/``db_skipped`` signal.
        """
        response = await self._client.request("PUT", self._task_url(entity_name), json=body)
        return response.json(), response.status_code == 201

    @override
    async def publish_task(
        self,
        task_dir: Path,
        tags: set[str] | None = None,
        visibility: str = "public",
    ) -> PublishResult:
        paths = TaskPaths(task_dir)
        if not paths.config_path.exists():
            raise FileNotFoundError(f"task.toml not found in {task_dir}")

        config = TaskConfig.model_validate_toml(paths.config_path.read_text())
        if config.task is None:
            raise ValueError("task.toml must contain a [task] section with a name")
        if not paths.environment_dir.exists():
            raise ValueError(f"Task directory {task_dir} is missing environment/.")
        try:
            Task(task_dir)
        except FileNotFoundError as exc:
            raise ValueError(str(exc)) from exc

        try:
            entity_name = to_entity_name(config.task.org, config.task.short_name)
        except NameMappingError as exc:
            # On the publish path this is a real, actionable failure rather than a miss, so it
            # is reported as one instead of riding out as the read path's "not found".
            raise PublishBackendError(str(exc)) from exc

        applied_tags = {LATEST_TAG} | (tags or set())
        build_start = time.monotonic()
        content_hash, files = Packager.compute_content_hash(task_dir)

        # Preflight *before* building the archive: if this exact content is already the task's
        # current spec, there is nothing to package or upload. Tags may still need to move, so
        # this decides whether to skip the build — not whether to skip the request.
        existing = await self._get_task(entity_name)
        existing_spec = (existing or {}).get("spec") or {}
        content_already_published = (
            existing_spec.get("kind") == "harbor"
            and existing_spec.get("archive_digest") == content_hash
        )

        archive_size = 0
        upload_time = 0.0
        if content_already_published:
            archive_ref = existing_spec["archive_ref"]
            build_time = time.monotonic() - build_start
            existing_tags = (existing or {}).get("tags") or {}
            existing_revision = (existing or {}).get("revision")
            if all(existing_tags.get(tag) == existing_revision for tag in applied_tags):
                # Nothing at all to do: same content, same tags. No request, no upload.
                return PublishResult(
                    name=config.task.name,
                    content_hash=content_hash,
                    archive_path=archive_ref,
                    file_count=len(files),
                    archive_size_bytes=0,
                    build_time_sec=round(build_time, 3),
                    upload_time_sec=0.0,
                    rpc_time_sec=0.0,
                    skipped=True,
                    revision=None,
                    tags=sorted(applied_tags),
                    db_skipped=True,
                )
        else:
            remote_path = self.remote_path(config.task.name, content_hash, ARCHIVE_FILENAME)
            with tempfile.TemporaryDirectory() as tmp:
                archive_path = Path(tmp) / ARCHIVE_FILENAME
                self._create_archive(task_dir, files, archive_path)
                archive_size = archive_path.stat().st_size
                build_time = time.monotonic() - build_start

                upload_start = time.monotonic()
                # Upload the blob *before* registering the task. The reverse order would let a
                # crash in between leave a task pointing at an archive that was never written,
                # and every later publish would then see matching content and report "skipped"
                # forever. An orphaned blob is inert by comparison.
                await self.storage.upload_file(archive_path, remote_path)
                upload_time = time.monotonic() - upload_start
            archive_ref = self.storage.to_fileset_ref(remote_path)

        instruction: str | None
        if paths.instruction_path.exists():
            instruction = paths.instruction_path.read_text()
        elif config.steps:
            instruction = None
        else:
            instruction = ""

        body = {
            "spec": {
                "kind": "harbor",
                "archive_ref": archive_ref,
                "archive_digest": content_hash,
                "instruction": instruction,
                # Stored whole rather than shredded into per-field columns. Nothing on the
                # read path needs it — `resolve_version` returns a path and a hash — so
                # modelling Harbor's schema here would be cost without a consumer, and it
                # would go stale the first time Harbor added a field.
                "config": config.model_dump(mode="json"),
            },
            "metadata": _metadata(
                {
                    PACKAGE_NAME_METADATA_KEY: config.task.name,
                    VISIBILITY_METADATA_KEY: visibility,
                }
            ),
            "tags": sorted(applied_tags - {LATEST_TAG}),
        }

        rpc_start = time.monotonic()
        if existing is None:
            try:
                response = await self._client.request(
                    "POST", self._task_url(entity_name), json=body
                )
                task, created = response.json(), True
            except PublishBackendError as exc:
                # A concurrent publisher created it between our preflight and here. `publish_tasks`
                # runs 50-wide, so this is a live race, not a theoretical one.
                if "already exists" not in str(exc).lower():
                    raise
                task, created = await self._put_task(entity_name, body)
        else:
            task, created = await self._put_task(entity_name, body)
        rpc_time = time.monotonic() - rpc_start

        return PublishResult(
            name=config.task.name,
            content_hash=content_hash,
            archive_path=archive_ref,
            file_count=len(files),
            archive_size_bytes=archive_size,
            build_time_sec=round(build_time, 3),
            upload_time_sec=round(upload_time, 3),
            rpc_time_sec=round(rpc_time, 3),
            skipped=not created,
            revision=task.get("revision") if created else None,
            tags=sorted(applied_tags),
            db_skipped=not created,
        )

    @override
    async def publish_dataset(
        self,
        dataset_dir: Path,
        tags: set[str] | None = None,
        visibility: str = "public",
        promote_tasks: bool = False,
    ) -> DatasetPublishResult:
        paths = DatasetPaths(dataset_dir)
        if not paths.manifest_path.exists():
            raise FileNotFoundError(f"dataset.toml not found in {dataset_dir}")

        manifest = DatasetManifest.from_toml_file(paths.manifest_path)
        try:
            entity_name = to_entity_name(manifest.dataset.org, manifest.dataset.short_name)
        except NameMappingError as exc:
            raise PublishBackendError(str(exc)) from exc

        applied_tags = {LATEST_TAG} | (tags or set())

        file_infos: list[dict[str, Any]] = []
        for file_ref in manifest.files:
            file_path = dataset_dir / file_ref.path
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Dataset file '{file_ref.path}' not found in {dataset_dir}"
                )
            result = await self.publish_file(manifest.dataset.name, file_path)
            file_infos.append(
                {
                    "path": file_ref.path,
                    "content_hash": result.content_hash,
                    "size_bytes": result.file_size_bytes,
                    "storage_path": result.remote_path,
                }
            )

        task_refs: list[str] = []
        for ref in manifest.tasks:
            try:
                member = to_entity_name(ref.org, ref.short_name)
            except NameMappingError as exc:
                raise PublishBackendError(str(exc)) from exc

            # A Harbor manifest always carries a `sha256:` pin (the field is required), and
            # dropping it would make a published dataset resolve to whatever its members'
            # `latest` happens to be later — silently changing what a dataset means. Translate
            # the archive digest into the revision digest a taskset pins by.
            try:
                revision_digest = await self._resolver.revision_digest_for_archive(
                    ref.org, ref.short_name, ref.digest
                )
            except ValueError as exc:
                raise PublishBackendError(
                    f"Dataset {manifest.dataset.name} pins {ref.name} at {ref.digest}, "
                    f"which is not published here: {exc}"
                ) from exc
            task_refs.append(f"{self._config.workspace}/{member}#{revision_digest}")

        body = {
            "description": manifest.dataset.description or None,
            "tasks": task_refs,
            "metadata": _metadata(
                {
                    PACKAGE_NAME_METADATA_KEY: manifest.dataset.name,
                    VISIBILITY_METADATA_KEY: visibility,
                    DATASET_FILES_METADATA_KEY: json.dumps(file_infos),
                }
            ),
            "tags": sorted(applied_tags - {LATEST_TAG}),
        }

        rpc_start = time.monotonic()
        try:
            existing = await self._client.get_json(self._taskset_url(entity_name))
        except NotFound:
            existing = None

        if existing is None:
            try:
                response = await self._client.request(
                    "POST", self._taskset_url(entity_name), json=body
                )
                created = True
            except PublishBackendError as exc:
                if "already exists" not in str(exc).lower():
                    raise
                response = await self._client.request(
                    "PUT", self._taskset_url(entity_name), json=body
                )
                created = response.status_code == 201
        else:
            response = await self._client.request(
                "PUT", self._taskset_url(entity_name), json=body
            )
            created = response.status_code == 201
        rpc_time = time.monotonic() - rpc_start
        taskset = response.json()

        return DatasetPublishResult(
            name=manifest.dataset.name,
            content_hash=await self._revision_hash(entity_name, taskset.get("revision")),
            revision=taskset.get("revision") or 0,
            task_count=manifest.task_count,
            file_count=len(file_infos),
            skipped=not created,
            db_skipped=not created,
            rpc_time_sec=round(rpc_time, 3),
            tags=sorted(applied_tags),
        )

    async def _revision_hash(self, entity_name: str, revision: int | None) -> str:
        """The taskset revision's content digest, for the publish report.

        Best effort: this is display data on a result that has already succeeded, so a failure
        to read it back must not turn a completed publish into an error.
        """
        if revision is None:
            return ""
        try:
            listing = await self._client.get_json(f"{self._taskset_url(entity_name)}/revisions")
        except Exception:  # noqa: BLE001 - see docstring
            return ""
        for entry in listing.get("data", []):
            if entry.get("revision") == revision:
                return entry.get("content_hash", "")
        return ""
