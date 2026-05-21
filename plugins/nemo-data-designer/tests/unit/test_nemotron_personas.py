# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Generator
from unittest.mock import Mock, patch

import pytest
from data_designer_nemo.nemotron_personas import (
    WORKSPACE,
    get_resource_name_for_locale,
    sync_nemotron_personas_fileset,
)
from nemo_platform import NeMoPlatform
from nemo_platform.types.files import NGCStorageConfig
from nmp.core.files.service import FilesService
from nmp.core.secrets.service import SecretsService
from nmp.testing import create_test_client

API_KEY_SECRET = "system/ngc-api-key"


@pytest.fixture
def mock_ngc_client() -> Generator[dict[str, Mock]]:
    with (
        patch("nmp.core.files.app.backends.ngc.Client") as mock_client_cls,
        patch("nmp.core.files.app.backends.ngc.ResourceAPI") as mock_resource_api_cls,
    ):
        mock_client = Mock()
        mock_resource_api = Mock()

        # `nemo-data-designer` no longer pins NGC versions when creating filesets
        # (see commit 7399308); the NGC backend resolves "latest" by calling
        # `list_versions(...)` and reading `.versionId` off the first entry, so
        # the mock must yield a fresh iterator of version-shaped objects on
        # every call (each backend instance re-resolves and consumes the
        # iterator once).
        mock_version = Mock()
        mock_version.versionId = "0.0.2"
        mock_resource_api.list_versions.side_effect = lambda *_a, **_kw: iter([mock_version])

        mock_client_cls.return_value = mock_client
        mock_resource_api_cls.return_value = mock_resource_api

        yield {
            "client": mock_client,
            "resource_api": mock_resource_api,
        }


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch, mock_ngc_client: dict[str, Mock]) -> Generator[NeMoPlatform]:
    with create_test_client(
        FilesService,
        SecretsService,
        client_type=NeMoPlatform,
    ) as sdk:
        monkeypatch.setenv("NGC_API_KEY", "nvapi-abc123")
        yield sdk
        monkeypatch.delenv("NGC_API_KEY")


def test_sync_nemotron_personas_fileset_creates_one_locale(sdk: NeMoPlatform) -> None:
    result = sync_nemotron_personas_fileset(sdk=sdk, locale="en_US", api_key_secret=API_KEY_SECRET)

    assert result == "created"

    filesets = sdk.files.filesets.list(workspace=WORKSPACE)
    assert [fileset.name for fileset in filesets.data] == [get_resource_name_for_locale("en_US")]


def test_sync_nemotron_personas_fileset_uses_api_key_secret(sdk: NeMoPlatform) -> None:
    sdk.secrets.create(workspace="system", name="custom-ngc-key", value="nvapi-custom123")

    sync_nemotron_personas_fileset(
        sdk=sdk,
        locale="en_US",
        api_key_secret="system/custom-ngc-key",
    )

    fileset = sdk.files.filesets.retrieve(name=get_resource_name_for_locale("en_US"), workspace=WORKSPACE)
    assert isinstance(fileset.storage, NGCStorageConfig)
    assert fileset.storage.api_key_secret == "system/custom-ngc-key"


def test_sync_nemotron_personas_fileset_preexisting_is_idempotent(sdk: NeMoPlatform) -> None:
    sync_nemotron_personas_fileset(sdk=sdk, locale="en_US", api_key_secret=API_KEY_SECRET)

    result = sync_nemotron_personas_fileset(sdk=sdk, locale="en_US", api_key_secret=API_KEY_SECRET)

    assert result == "exists"

    filesets = sdk.files.filesets.list(workspace=WORKSPACE)
    assert len(filesets.data) == 1


def test_sync_nemotron_personas_fileset_creation_failure_raises(
    sdk: NeMoPlatform, mock_ngc_client: dict[str, Mock]
) -> None:
    mock_ngc_client["client"].configure.side_effect = RuntimeError("Something goes wrong")

    with pytest.raises(Exception):
        sync_nemotron_personas_fileset(sdk=sdk, locale="en_US", api_key_secret=API_KEY_SECRET)

    filesets = sdk.files.filesets.list(workspace=WORKSPACE)
    assert len(filesets.data) == 0
