# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Reading Harbor datasets out of NeMo tasksets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, override

from harbor.models.package.reference import PackageReference
from harbor.models.registry import DatasetFileInfo, DatasetMetadata, DatasetSummary
from harbor.models.task.id import GitTaskId, LocalTaskId, PackageTaskId
from harbor.registry.client.base import BaseRegistryClient

from harbor_nemo.client import NemoClient, NotFound
from harbor_nemo.config import NemoConfig
from harbor_nemo.names import NameMappingError, from_entity_name, to_entity_name
from harbor_nemo.publisher import (
    DATASET_FILES_METADATA_KEY,
    PACKAGE_NAME_METADATA_KEY,
)
from harbor_nemo.storage import NemoStorage


#: Harbor writes content references as ``sha256:<hex>``; NeMo revision fragments are bare hex.
_SHA256_PREFIX = "sha256:"


def _strip_digest_prefix(ref: str) -> str:
    return ref[len(_SHA256_PREFIX) :] if ref.startswith(_SHA256_PREFIX) else ref


def _metadata_value(record: dict[str, Any], key: str) -> str | None:
    for item in record.get("metadata") or []:
        if item.get("key") == key:
            return item.get("value")
    return None


class NemoDatasetClient(BaseRegistryClient):
    """Resolves ``org/name@ref`` to dataset metadata backed by a NeMo taskset.

    Storage comes from the owning backend rather than being constructed here: a
    ``DatasetFileInfo.storage_path`` is a literal path issued by one fileset, so reading it
    from a different one would be a lookup for a blob that fileset never stored.
    """

    def __init__(self, client: NemoClient, config: NemoConfig, storage: NemoStorage) -> None:
        # BaseRegistryClient.__init__ builds the TaskClient that the inherited
        # `download_dataset` drives. Skipping it leaves that path broken.
        super().__init__()
        self._client = client
        self._config = config
        self._storage = storage

    def _taskset_url(self, entity_name: str) -> str:
        return f"{self._config.tasksets_url}/{entity_name}"

    async def _member_archive_digest(self, ref: str) -> tuple[str, str, str]:
        """Resolve a taskset member reference to ``(org, name, archive_digest)``.

        A taskset pins members by NeMo *revision* digest, while a Harbor dataset pins tasks by
        the *archive* hash, so every member needs a fetch to read ``spec.archive_digest`` out
        of the revision the taskset actually named. There is no way to answer this from the
        taskset alone.
        """
        location, _, fragment = ref.partition("#")
        workspace, _, entity_name = location.partition("/")
        if not entity_name:
            workspace, entity_name = self._config.workspace, workspace

        url = f"{self._config.base_url}/apis/evaluator/v2/workspaces/{workspace}/tasks/{entity_name}"
        if fragment:
            url = f"{url}/revisions/{_strip_digest_prefix(fragment)}"
        task = await self._client.get_json(url)

        spec = task.get("spec") or {}
        if spec.get("kind") != "harbor":
            raise ValueError(
                f"Taskset member {ref!r} is a {spec.get('kind')!r} task, not a Harbor package."
            )
        org, name = from_entity_name(entity_name)
        return org, name, spec["archive_digest"]

    @override
    async def _get_dataset_metadata(self, name: str) -> DatasetMetadata:
        reference = PackageReference.parse(name)
        try:
            entity_name = to_entity_name(reference.org, reference.short_name)
        except NameMappingError as exc:
            raise ValueError(str(exc)) from exc

        url = self._taskset_url(entity_name)
        if reference.ref:
            # Strip Harbor's `sha256:` prefix. NeMo writes a revision digest as bare hex
            # precisely so a `#` fragment stays free of ':', which the entity-ref charset does
            # not admit — and the route's own path pattern rejects it with a 422, not a 404.
            # This matters beyond hand-typed refs: `version` on the metadata we return carries
            # the prefix (Harbor's convention), and Harbor feeds it straight back in when it
            # re-resolves a dataset, which is how `harbor run -d` hit it.
            url = f"{url}/revisions/{_strip_digest_prefix(reference.ref)}"

        try:
            taskset = await self._client.get_json(url)
        except NotFound as exc:
            # The not-found contract: `package_type` distinguishes absent from broken on
            # exactly this, and the dataset probe runs first, so a wrong exception type here
            # would stop a task from ever being found.
            raise ValueError(f"Dataset not found: {name}") from exc

        task_ids: list[GitTaskId | LocalTaskId | PackageTaskId] = []
        for member in taskset.get("tasks") or []:
            org, short_name, digest = await self._member_archive_digest(member)
            task_ids.append(PackageTaskId(org=org, name=short_name, ref=f"sha256:{digest}"))

        files: list[DatasetFileInfo] = []
        raw_files = _metadata_value(taskset, DATASET_FILES_METADATA_KEY)
        if raw_files:
            for entry in json.loads(raw_files):
                files.append(
                    DatasetFileInfo(
                        path=entry["path"],
                        storage_path=entry["storage_path"],
                        content_hash=entry["content_hash"],
                    )
                )

        revisions = await self._revision_hash(entity_name, taskset.get("revision"))
        return DatasetMetadata(
            name=_metadata_value(taskset, PACKAGE_NAME_METADATA_KEY) or reference.name,
            version=f"sha256:{revisions}" if revisions else None,
            description=taskset.get("description") or "",
            task_ids=task_ids,
            metrics=[],
            files=files,
            dataset_version_id=f"{self._config.workspace}/{entity_name}#{taskset.get('revision')}",
            dataset_version_content_hash=revisions or None,
        )

    async def _revision_hash(self, entity_name: str, revision: int | None) -> str:
        if revision is None:
            return ""
        try:
            listing = await self._client.get_json(f"{self._taskset_url(entity_name)}/revisions")
        except NotFound:
            return ""
        for entry in listing.get("data", []):
            if entry.get("revision") == revision:
                return entry.get("content_hash", "")
        return ""

    @override
    async def list_datasets(self) -> list[DatasetSummary]:
        listing = await self._client.get_json(
            self._config.tasksets_url, params={"page_size": 100}
        )
        summaries: list[DatasetSummary] = []
        for taskset in listing.get("data", []):
            entity_name = taskset.get("name", "")
            try:
                org, short_name = from_entity_name(entity_name)
                harbor_name = f"{org}/{short_name}"
            except NameMappingError:
                # A taskset created outside Harbor has no org prefix. Listing it under its raw
                # name is more useful than hiding it or failing the whole listing.
                harbor_name = entity_name
            summaries.append(
                DatasetSummary(
                    name=_metadata_value(taskset, PACKAGE_NAME_METADATA_KEY) or harbor_name,
                    description=taskset.get("description") or "",
                    task_count=len(taskset.get("tasks") or []),
                )
            )
        return summaries

    @override
    async def download_dataset_files(
        self,
        metadata: DatasetMetadata,
        overwrite: bool = False,
        output_dir: Path | None = None,
    ) -> dict[str, Path]:
        from harbor.constants import DATASET_CACHE_DIR

        if not metadata.files:
            return {}

        if output_dir is not None:
            cache_dir = output_dir
        else:
            org, _, short_name = metadata.name.partition("/")
            version = metadata.dataset_version_content_hash or "unversioned"
            cache_dir = DATASET_CACHE_DIR / org / short_name / version

        result: dict[str, Path] = {}
        for file_info in metadata.files:
            local_path = cache_dir / file_info.path
            if not local_path.exists() or overwrite:
                await self._storage.download_file(file_info.storage_path, local_path)
            result[file_info.path] = local_path
        return result
