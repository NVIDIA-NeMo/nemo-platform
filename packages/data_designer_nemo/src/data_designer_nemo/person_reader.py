# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import duckdb
from data_designer.engine.resources.person_reader import PersonReader
from data_designer_nemo.nemotron_personas import (
    get_locale_fileset_file_ref,
)
from data_designer_nemo.sdk_translation import async_to_sync_sdk
from nemo_platform import AsyncNeMoPlatform, NeMoPlatform


class FilesetsPersonReader(PersonReader):
    """Provides DuckDB access to Nemotron personas datasets via filesets.

    Accepts either a sync :class:`NeMoPlatform` (job-container path, sync
    top-level) or an :class:`AsyncNeMoPlatform` (API-process path, used
    from a worker thread under :func:`anyio.to_thread.run_sync`).

    DuckDB calls into the SDK fileset filesystem synchronously, so when this
    reader is constructed with an async SDK we rebuild a sync SDK first. Auth
    and identity propagate; fsspec stays in sync mode.
    """

    def __init__(self, sdk: NeMoPlatform | AsyncNeMoPlatform):
        if isinstance(sdk, AsyncNeMoPlatform):
            sdk = async_to_sync_sdk(sdk)
        self._sdk = sdk

    def create_duckdb_connection(self) -> duckdb.DuckDBPyConnection:
        conn = duckdb.connect()
        conn.register_filesystem(self._sdk.files.fsspec)
        return conn

    def get_dataset_uri(self, locale: str) -> str:
        return f"fileset://{get_locale_fileset_file_ref(locale)}"
