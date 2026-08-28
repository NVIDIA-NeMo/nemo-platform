# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fileset staging helpers shared by Anonymizer CLI verbs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Generic, TypeVar

import typer
from filesets import build_fileset_ref
from nemo_anonymizer_plugin.app.errors import AnonymizerInvalidConfigError
from nemo_anonymizer_plugin.app.input import classify_input_source
from nemo_anonymizer_plugin.app.task_config import AnonymizerRequest
from nemo_platform import NeMoPlatform
from nemo_platform_plugin.client.adapter import client_from_platform
from nemo_platform_plugin.files.client import FilesClient
from nemo_platform_plugin.files.types import CreateFilesetRequest

AnonymizerRequestT = TypeVar("AnonymizerRequestT", bound=AnonymizerRequest)

_SUPPORTED_INPUT_FILE_SUFFIXES = {".csv", ".parquet"}


@dataclass(frozen=True)
class StagedAnonymizerRequest(Generic[AnonymizerRequestT]):
    request: AnonymizerRequestT
    source_was_local: bool


def make_platform_client(*, base_url: str, workspace: str, headers: dict[str, str]) -> NeMoPlatform:
    return NeMoPlatform(base_url=base_url, workspace=workspace, default_headers=headers or None)


def stage_anonymizer_request_for_remote(
    request: AnonymizerRequestT,
    *,
    platform_client: NeMoPlatform | None,
    workspace: str,
    fileset: str | None,
    input_remote_path: str | None,
    upload: bool,
    quiet: bool = False,
) -> StagedAnonymizerRequest[AnonymizerRequestT]:
    source_kind = classify_input_source_for_cli(request.data.source)
    if source_kind != "local":
        return StagedAnonymizerRequest(request=request, source_was_local=False)
    if fileset is None:
        raise ValueError("Local input sources require --fileset so the CLI can upload the file for remote execution.")

    local_path = resolve_local_input_path(request.data.source)
    remote_path = resolve_input_remote_path(input_remote_path, local_path)
    if upload:
        if platform_client is None:
            raise ValueError("Local input upload requires a platform client.")
        ensure_fileset_exists(platform_client, workspace=workspace, fileset=fileset)
        upload_file_to_fileset(
            platform_client,
            local_path=local_path,
            remote_path=remote_path,
            fileset=fileset,
            workspace=workspace,
            description="local input",
            quiet=quiet,
        )

    data = request.data.model_copy(
        update={
            "source": build_fileset_ref(remote_path, workspace=workspace, fileset=fileset),
        }
    )
    return StagedAnonymizerRequest(
        request=request.model_copy(update={"data": data}),
        source_was_local=True,
    )


def classify_input_source_for_cli(source: str) -> str:
    try:
        return classify_input_source(source)
    except AnonymizerInvalidConfigError as exc:
        raise ValueError(str(exc)) from exc


def resolve_local_input_path(source: str) -> Path:
    path = Path(source).expanduser()
    if not path.is_file():
        raise ValueError(f"Local input source {source!r} must point to an existing file.")
    validate_input_file_suffix(str(path), label=f"Local input source {source!r}")
    return path


def resolve_input_remote_path(input_remote_path: str | None, local_path: Path) -> str:
    remote_path = input_remote_path or local_path.name
    normalized = validate_remote_file_path(remote_path, option_name="--input-remote-path")
    validate_input_file_suffix(normalized, label=f"--input-remote-path {normalized!r}")
    return normalized


def validate_input_file_suffix(path: str, *, label: str) -> None:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in _SUPPORTED_INPUT_FILE_SUFFIXES:
        expected = ", ".join(sorted(_SUPPORTED_INPUT_FILE_SUFFIXES))
        raise ValueError(f"{label} must be one of: {expected}.")


def validate_remote_file_path(remote_path: str, *, option_name: str) -> str:
    normalized = remote_path.strip()
    if not normalized:
        raise ValueError(f"{option_name} must not be empty.")
    if normalized.startswith("/"):
        raise ValueError(f"{option_name} must be relative to the fileset root.")
    if normalized.endswith("/"):
        raise ValueError(f"{option_name} must include a file name.")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError(f"{option_name} must not include parent-directory segments.")
    return normalized


def ensure_fileset_exists(platform_client: NeMoPlatform, *, workspace: str, fileset: str) -> None:
    files = client_from_platform(platform_client, FilesClient)
    files.create_fileset(
        workspace=workspace,
        body=CreateFilesetRequest(name=fileset),
        exist_ok=True,
    )


def upload_file_to_fileset(
    platform_client: NeMoPlatform,
    *,
    local_path: Path,
    remote_path: str,
    fileset: str,
    workspace: str,
    description: str,
    quiet: bool = False,
) -> None:
    if not quiet:
        typer.echo(f"Uploading {description} to {fileset}#{remote_path}", err=True)
    platform_client.files.upload(
        local_path=str(local_path),
        remote_path=remote_path,
        fileset=fileset,
        workspace=workspace,
    )
