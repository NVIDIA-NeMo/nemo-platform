"""E2E tests for external storage backends (NGC, Hugging Face).

These tests verify that the files service can create filesets backed by
external storage providers and read files from them via the SDK.

NGC tests require ``NGC_API_KEY`` in the environment and are skipped
otherwise.  Hugging Face tests use a small public repo; when ``HF_TOKEN``
is set the request is authenticated (avoids rate-limits in CI).
"""

import os
import tempfile
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from nemo_platform import BadRequestError, NeMoPlatform
from nemo_platform.types.files import HuggingfaceStorageConfigParam, NGCStorageConfigParam

# ---------------------------------------------------------------------------
# NGC configuration
# ---------------------------------------------------------------------------
NGC_ORG = "nvidia"
NGC_TEAM = "nemo-microservices"
NGC_TARGET = "nemo-microservices-quickstart"
NGC_TARGET_TYPE = "resource"

# ---------------------------------------------------------------------------
# Hugging Face configuration — small public model
# ---------------------------------------------------------------------------
HF_TOKEN_ENV = "HF_TOKEN"

HF_REPO_ID = "hf-internal-testing/tiny-random-bert"
HF_REPO_TYPE = "model"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ngc_fileset(sdk: NeMoPlatform, workspace: str, ngc_secret: str) -> Iterator[str]:
    """Create an NGC-backed fileset, cleaned up after test."""
    fileset_name = f"e2e-ngc-fs-{uuid.uuid4().hex[:8]}"
    sdk.files.filesets.create(
        workspace=workspace,
        name=fileset_name,
        description="E2E test NGC-backed fileset",
        storage=NGCStorageConfigParam(
            api_key_secret=ngc_secret,
            org=NGC_ORG,
            team=NGC_TEAM,
            target=NGC_TARGET,
            target_type=NGC_TARGET_TYPE,
        ),
    )
    yield fileset_name
    try:
        sdk.files.filesets.delete(fileset_name, workspace=workspace)
    except Exception:
        pass  # Best-effort cleanup; the workspace is deleted anyway


@pytest.fixture
def hf_token() -> str:
    """Return the HF token from the environment."""
    token = os.environ.get(HF_TOKEN_ENV)
    assert token, f"{HF_TOKEN_ENV} must be set"
    return token


@pytest.fixture
def hf_secret(sdk: NeMoPlatform, workspace: str, hf_token: str) -> Iterator[str]:
    """Create a secret containing the HF token, cleaned up after test."""
    secret_name = f"e2e-hf-tok-{uuid.uuid4().hex[:8]}"
    sdk.secrets.create(workspace=workspace, name=secret_name, value=hf_token)
    yield secret_name
    try:
        sdk.secrets.delete(workspace=workspace, name=secret_name)
    except Exception:
        pass  # Best-effort cleanup; the workspace is deleted anyway


@pytest.fixture
def hf_fileset(sdk: NeMoPlatform, workspace: str, hf_secret: str) -> Iterator[str]:
    """Create a Hugging Face-backed fileset, cleaned up after test."""
    fileset_name = f"e2e-hf-fs-{uuid.uuid4().hex[:8]}"

    storage = HuggingfaceStorageConfigParam(
        repo_id=HF_REPO_ID,
        repo_type=HF_REPO_TYPE,
        token_secret=hf_secret,
    )

    sdk.files.filesets.create(
        workspace=workspace,
        name=fileset_name,
        description="E2E test HF-backed fileset",
        storage=storage,
    )
    yield fileset_name
    try:
        sdk.files.filesets.delete(fileset_name, workspace=workspace)
    except Exception:
        pass  # Best-effort cleanup; the workspace is deleted anyway


# ===================================================================
# NGC tests
# ===================================================================


class TestNGCFileset:
    """Tests for NGC-backed filesets."""

    def test_list_files(self, sdk: NeMoPlatform, workspace: str, ngc_fileset: str):
        """Listing an NGC-backed fileset returns files with paths and sizes."""
        files = sdk.files.list(fileset=ngc_fileset, workspace=workspace)
        assert len(files.data) > 0, "NGC fileset should contain at least one file"

        for f in files.data:
            assert f.path, "Each file should have a path"
            assert f.size > 0, "Each file should have a non-zero size"

    def test_download_file(self, sdk: NeMoPlatform, workspace: str, ngc_fileset: str):
        """Downloading the smallest file from an NGC fileset succeeds and size matches."""
        files = sdk.files.list(fileset=ngc_fileset, workspace=workspace)
        assert len(files.data) > 0

        target = min(files.data, key=lambda f: f.size)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / target.path.replace("/", "_")
            sdk.files.download(
                fileset=ngc_fileset,
                workspace=workspace,
                remote_path=target.path,
                local_path=str(local_path),
            )
            assert local_path.exists()
            assert local_path.stat().st_size == target.size

    def test_cache_status(self, sdk: NeMoPlatform, workspace: str, ngc_fileset: str):
        """NGC-backed files report a cacheable status."""
        files = sdk.files.list(
            fileset=ngc_fileset,
            workspace=workspace,
            include_cache_status=True,
        )
        assert len(files.data) > 0

        for f in files.data:
            assert f.cache_status is not None
            assert f.cache_status != "not_cacheable"

    # -- error cases --

    @pytest.mark.parametrize(
        ("secret_value", "storage_overrides", "match"),
        [
            pytest.param(
                "not-a-real-key",
                {},
                "Invalid API key. Legacy NGC keys are not supported.",
                id="invalid-key-prefix",
            ),
            pytest.param(
                None,
                {"org": "nvidian", "team": "nemo-llm", "target": "nemo-platform-quickstart"},
                "Error creating NGC storage backend:",
                id="wrong-org",
            ),
            pytest.param(
                None,
                {"target": "this-resource-does-not-exist-12345"},
                "Failed to access NGC resource this-resource-does-not-exist-12345",
                id="nonexistent-resource",
            ),
        ],
    )
    def test_create_error(
        self,
        sdk: NeMoPlatform,
        workspace: str,
        ngc_api_key: str,
        secret_value: str | None,
        storage_overrides: dict,
        match: str,
    ):
        """Bad NGC configurations are rejected with 400."""
        value = secret_value if secret_value is not None else ngc_api_key
        secret_name = f"e2e-ngc-err-{uuid.uuid4().hex[:8]}"
        sdk.secrets.create(workspace=workspace, name=secret_name, value=value)
        try:
            storage = NGCStorageConfigParam(
                api_key_secret=secret_name,
                org=storage_overrides.get("org", NGC_ORG),
                team=storage_overrides.get("team", NGC_TEAM),
                target=storage_overrides.get("target", NGC_TARGET),
                target_type=NGC_TARGET_TYPE,
            )
            with pytest.raises(BadRequestError, match=match):
                sdk.files.filesets.create(
                    workspace=workspace,
                    name=f"e2e-ngc-err-{uuid.uuid4().hex[:8]}",
                    storage=storage,
                )
        finally:
            sdk.secrets.delete(workspace=workspace, name=secret_name)

    def test_create_error_nonexistent_secret(self, sdk: NeMoPlatform, workspace: str):
        """Referencing a secret that doesn't exist is rejected with 400."""
        with pytest.raises(BadRequestError, match="Secret not found:"):
            sdk.files.filesets.create(
                workspace=workspace,
                name=f"e2e-ngc-err-{uuid.uuid4().hex[:8]}",
                storage=NGCStorageConfigParam(
                    api_key_secret="no-such-secret-99999",
                    org=NGC_ORG,
                    team=NGC_TEAM,
                    target=NGC_TARGET,
                    target_type=NGC_TARGET_TYPE,
                ),
            )


# ===================================================================
# Hugging Face tests
# ===================================================================


@pytest.mark.skipif(not os.environ.get(HF_TOKEN_ENV), reason=f"{HF_TOKEN_ENV} not set")
class TestHuggingFaceFileset:
    """Tests for Hugging Face-backed filesets."""

    def test_list_files(self, sdk: NeMoPlatform, workspace: str, hf_fileset: str):
        """Listing an HF-backed fileset returns files with paths and sizes."""
        files = sdk.files.list(fileset=hf_fileset, workspace=workspace)
        assert len(files.data) > 0, "HF fileset should contain at least one file"

        for f in files.data:
            assert f.path, "Each file should have a path"
            assert f.size > 0, "Each file should have a non-zero size"

    def test_download_file(self, sdk: NeMoPlatform, workspace: str, hf_fileset: str):
        """Downloading the smallest file from an HF fileset succeeds and size matches."""
        files = sdk.files.list(fileset=hf_fileset, workspace=workspace)
        assert len(files.data) > 0

        target = min(files.data, key=lambda f: f.size)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = Path(tmpdir) / target.path.replace("/", "_")
            sdk.files.download(
                fileset=hf_fileset,
                workspace=workspace,
                remote_path=target.path,
                local_path=str(local_path),
            )
            assert local_path.exists()
            assert local_path.stat().st_size == target.size

    def test_cache_status(self, sdk: NeMoPlatform, workspace: str, hf_fileset: str):
        """HF-backed files report a cacheable status."""
        files = sdk.files.list(
            fileset=hf_fileset,
            workspace=workspace,
            include_cache_status=True,
        )
        assert len(files.data) > 0

        for f in files.data:
            assert f.cache_status is not None
            assert f.cache_status != "not_cacheable"

    # -- error cases --

    def test_error_nonexistent_repo(self, sdk: NeMoPlatform, workspace: str):
        """Pointing at a repo that doesn't exist is rejected with 400."""
        with pytest.raises(BadRequestError):
            sdk.files.filesets.create(
                workspace=workspace,
                name=f"e2e-hf-err-{uuid.uuid4().hex[:8]}",
                storage=HuggingfaceStorageConfigParam(
                    repo_id="this-org-does-not-exist/this-repo-does-not-exist-12345",
                    repo_type="model",
                ),
            )
