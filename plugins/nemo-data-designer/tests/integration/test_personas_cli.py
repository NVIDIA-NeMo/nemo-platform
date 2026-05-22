# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from collections.abc import Generator
from unittest.mock import Mock, patch

import nemo_data_designer_plugin.testing.utils as u
import pytest
from data_designer_nemo.nemotron_personas import WORKSPACE, get_resource_name_for_locale
from nemo_data_designer_plugin.cli import personas as personas_module
from nemo_platform import NeMoPlatform
from nemo_platform.types.files import NGCStorageConfig

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_ngc_client() -> Generator[dict[str, Mock]]:
    with (
        patch("nmp.core.files.app.backends.ngc.Client") as mock_client_cls,
        patch("nmp.core.files.app.backends.ngc.ResourceAPI") as mock_resource_api_cls,
    ):
        mock_client = Mock()
        mock_resource_api = Mock()

        mock_client_cls.return_value = mock_client
        mock_resource_api_cls.return_value = mock_resource_api

        yield {
            "client": mock_client,
            "resource_api": mock_resource_api,
        }


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch, mock_ngc_client: dict[str, Mock]) -> Generator[NeMoPlatform]:
    with u.make_mock_client_context() as client_context:
        monkeypatch.setenv("NGC_API_KEY", "nvapi-abc123")
        yield client_context.sdk
        monkeypatch.delenv("NGC_API_KEY")


@pytest.fixture
def cli_sdk(monkeypatch: pytest.MonkeyPatch, sdk: NeMoPlatform) -> NeMoPlatform:
    monkeypatch.setattr(personas_module, "NeMoPlatform", lambda: sdk)
    return sdk


def test_personas_download_is_wired_properly() -> None:
    result = u.invoke_cli(["personas", "download", "--help"])

    assert result.exit_code == 0, result.output
    assert "nemo data-designer personas download --list" in result.output
    assert "data-designer download personas" not in result.output


def test_make_fileset_creates_requested_locale_with_existing_secret(cli_sdk: NeMoPlatform) -> None:
    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "en_US",
            "--api-key-secret",
            "system/ngc-api-key",
        ]
    )

    assert result.exit_code == 0, result.output
    filesets = cli_sdk.files.filesets.list(workspace=WORKSPACE)
    assert [fileset.name for fileset in filesets.data] == [get_resource_name_for_locale("en_US")]

    fileset = cli_sdk.files.filesets.retrieve(name=get_resource_name_for_locale("en_US"), workspace=WORKSPACE)
    assert isinstance(fileset.storage, NGCStorageConfig)
    assert fileset.storage.api_key_secret == "system/ngc-api-key"


def test_make_fileset_creates_secret_from_env_then_fileset(
    monkeypatch: pytest.MonkeyPatch, cli_sdk: NeMoPlatform
) -> None:
    monkeypatch.setenv("MY_NGC_API_KEY", "nvapi-from-env")

    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "en_US",
            "--api-key-secret",
            "system/my-ngc-key",
            "--api-key-env-var",
            "MY_NGC_API_KEY",
        ]
    )

    assert result.exit_code == 0, result.output
    secret = cli_sdk.secrets.access("my-ngc-key", workspace="system")
    assert secret.value == "nvapi-from-env"

    fileset = cli_sdk.files.filesets.retrieve(name=get_resource_name_for_locale("en_US"), workspace=WORKSPACE)
    assert isinstance(fileset.storage, NGCStorageConfig)
    assert fileset.storage.api_key_secret == "system/my-ngc-key"


def test_make_fileset_missing_env_var() -> None:
    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "en_US",
            "--api-key-secret",
            "system/my-ngc-key",
            "--api-key-env-var",
            "MISSING_NGC_API_KEY",
        ]
    )

    assert result.exit_code != 0
    assert "MISSING_NGC_API_KEY" in result.output
    assert "not set or is empty" in result.output


def test_make_fileset_unknown_locale() -> None:
    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "de_DE",
            "--api-key-secret",
            "system/ngc-api-key",
        ]
    )

    assert result.exit_code != 0
    assert "Invalid value for '--locale'" in result.output
    assert "de_DE" in result.output


def test_make_fileset_bare_secret_name() -> None:
    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "en_US",
            "--api-key-secret",
            "ngc-api-key",
        ]
    )

    assert result.exit_code != 0
    assert "WORKSPACE/NAME" in result.output


def test_make_fileset_create_secret_conflict_does_not_create_fileset(
    monkeypatch: pytest.MonkeyPatch, cli_sdk: NeMoPlatform
) -> None:
    cli_sdk.secrets.create(workspace="system", name="my-ngc-key", value="nvapi-existing")
    monkeypatch.setenv("MY_NGC_API_KEY", "nvapi-from-env")

    result = u.invoke_cli(
        [
            "personas",
            "make-fileset",
            "--locale",
            "en_US",
            "--api-key-secret",
            "system/my-ngc-key",
            "--api-key-env-var",
            "MY_NGC_API_KEY",
        ]
    )

    assert result.exit_code == 1
    assert "already exists" in result.output
    filesets = cli_sdk.files.filesets.list(workspace=WORKSPACE)
    assert filesets.data == []


def test_make_fileset_create_secret_internal_error_surfaces_clearly(
    monkeypatch: pytest.MonkeyPatch, cli_sdk: NeMoPlatform
) -> None:
    monkeypatch.setenv("MY_NGC_API_KEY", "nvapi-from-env")

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("secrets backend exploded")

    with patch.object(cli_sdk.secrets, "create", side_effect=_boom):
        result = u.invoke_cli(
            [
                "personas",
                "make-fileset",
                "--locale",
                "en_US",
                "--api-key-secret",
                "system/my-ngc-key",
                "--api-key-env-var",
                "MY_NGC_API_KEY",
            ]
        )

    assert result.exit_code == 1
    assert "Failed to create secret" in result.output
    assert "secrets backend exploded" in result.output
    filesets = cli_sdk.files.filesets.list(workspace=WORKSPACE)
    assert filesets.data == []
