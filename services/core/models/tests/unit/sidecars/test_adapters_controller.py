# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the LoRA adapters sidecar controller."""

import json
import os
import unittest.mock
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from nmp.core.models.sidecars.adapters.main import ADAPTER_META_FILENAME, AdaptersController


def _make_adapter(
    name: str,
    fileset: str,
    enabled: bool = True,
    updated_at: datetime | None = None,
    workspace: str = "default",
):
    """Helper to build a mock Adapter object.

    ``workspace`` defaults to ``"default"`` so tests that pre-create directories
    on disk can use the matching ``{workspace}--{name}`` encoding produced by
    :meth:`AdaptersController._update_lora_adapters`.
    """
    adapter = MagicMock()
    adapter.name = name
    adapter.fileset = fileset
    adapter.enabled = enabled
    adapter.updated_at = updated_at
    adapter.workspace = workspace
    return adapter


@pytest.fixture
def controller(tmp_path):
    """Create an AdaptersController with __init__ bypassed."""
    with patch.object(AdaptersController, "__init__", lambda self, **kwargs: None):
        ctrl = AdaptersController()
        ctrl.nim_peft_source = str(tmp_path)
        ctrl._sdk = MagicMock()
        ctrl.workspace = "default"
        ctrl.model_name = "base-model"
        # Default to NIM behavior (no rewrite); vLLM tests override this.
        ctrl.base_model_name_override = ""
        return ctrl


class TestAdapterChanged:
    """Tests for AdaptersController._adapter_changed."""

    def test_returns_true_when_meta_file_missing(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        adapter = _make_adapter("my-adapter", "ws/fileset-v1")

        assert controller._adapter_changed(adapter_dir, adapter) is True

    def test_returns_true_when_meta_file_corrupt(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        meta_path = os.path.join(adapter_dir, ADAPTER_META_FILENAME)
        with open(meta_path, "w") as f:
            f.write("not json{{{")

        adapter = _make_adapter("my-adapter", "ws/fileset-v1")
        assert controller._adapter_changed(adapter_dir, adapter) is True

    def test_returns_true_when_fileset_differs(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        meta = {"fileset": "ws/old-fileset", "updated_at": ts.isoformat()}
        with open(os.path.join(adapter_dir, ADAPTER_META_FILENAME), "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("my-adapter", "ws/new-fileset", updated_at=ts)
        assert controller._adapter_changed(adapter_dir, adapter) is True

    def test_returns_true_when_updated_at_differs(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        old_ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        new_ts = datetime(2026, 3, 15, tzinfo=timezone.utc)
        meta = {"fileset": "ws/fileset-v1", "updated_at": old_ts.isoformat()}
        with open(os.path.join(adapter_dir, ADAPTER_META_FILENAME), "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=new_ts)
        assert controller._adapter_changed(adapter_dir, adapter) is True

    def test_returns_false_when_metadata_matches(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        meta = {"fileset": "ws/fileset-v1", "updated_at": ts.isoformat()}
        with open(os.path.join(adapter_dir, ADAPTER_META_FILENAME), "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=ts)
        assert controller._adapter_changed(adapter_dir, adapter) is False

    def test_returns_false_when_both_updated_at_none(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        meta = {"fileset": "ws/fileset-v1", "updated_at": None}
        with open(os.path.join(adapter_dir, ADAPTER_META_FILENAME), "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None)
        assert controller._adapter_changed(adapter_dir, adapter) is False


class TestWriteAdapterMeta:
    """Tests for AdaptersController._write_adapter_meta."""

    def test_writes_metadata_with_timestamp(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        ts = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        adapter = _make_adapter("my-adapter", "ws/fileset-v2", updated_at=ts)

        controller._write_adapter_meta(adapter_dir, adapter)

        meta_path = os.path.join(adapter_dir, ADAPTER_META_FILENAME)
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["fileset"] == "ws/fileset-v2"
        assert meta["updated_at"] == ts.isoformat()

    def test_writes_metadata_with_none_timestamp(self, controller, tmp_path):
        adapter_dir = str(tmp_path / "my-adapter")
        os.makedirs(adapter_dir)
        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None)

        controller._write_adapter_meta(adapter_dir, adapter)

        meta_path = os.path.join(adapter_dir, ADAPTER_META_FILENAME)
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["fileset"] == "ws/fileset-v1"
        assert meta["updated_at"] is None


class TestDownloadAdapter:
    """Tests for AdaptersController._download_adapter atomic behavior."""

    def test_successful_download_creates_adapter_dir_atomically(self, controller, tmp_path):
        """Verify that a successful download creates the adapter dir via rename."""
        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None, workspace="ws")
        dir_name = "ws--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        controller._download_adapter(adapter_dir, adapter, "ws")

        assert os.path.isdir(adapter_dir)
        assert os.path.exists(os.path.join(adapter_dir, ADAPTER_META_FILENAME))
        temp_dirs = [e for e in os.listdir(tmp_path) if e.startswith(".")]
        assert temp_dirs == []

    def test_failed_download_cleans_up_temp_dir(self, controller, tmp_path):
        """Verify that a failed download (empty fileset) removes the temp dir."""
        adapter = _make_adapter("my-adapter", "default/empty-fs", updated_at=None)
        dir_name = "default--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        mock_files_response = MagicMock()
        mock_files_response.data = []
        controller._sdk.files.list.return_value = mock_files_response

        controller._download_adapter(adapter_dir, adapter, "default")

        assert not os.path.exists(adapter_dir)
        temp_dirs = [e for e in os.listdir(tmp_path) if e.startswith(".")]
        assert temp_dirs == []

    def test_exception_during_download_cleans_up_temp_dir(self, controller, tmp_path):
        """Verify that an exception during download removes the temp dir and re-raises."""
        adapter = _make_adapter("my-adapter", "default/bad-fs", updated_at=None)
        dir_name = "default--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        controller._sdk.files.list.side_effect = RuntimeError("network error")

        with pytest.raises(RuntimeError, match="network error"):
            controller._download_adapter(adapter_dir, adapter, "default")

        assert not os.path.exists(adapter_dir)
        temp_dirs = [e for e in os.listdir(tmp_path) if e.startswith(".")]
        assert temp_dirs == []

    def test_replaces_existing_adapter_dir_on_success(self, controller, tmp_path):
        """Verify that re-downloading replaces the old adapter directory."""
        dir_name = "default--my-adapter"
        adapter_dir = tmp_path / dir_name
        adapter_dir.mkdir()
        (adapter_dir / "old_file.bin").write_text("stale")

        adapter = _make_adapter("my-adapter", "default/new-fileset", updated_at=None)

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        controller._download_adapter(str(adapter_dir), adapter, "default")

        assert adapter_dir.is_dir()
        assert not (adapter_dir / "old_file.bin").exists()
        assert (adapter_dir / ADAPTER_META_FILENAME).exists()

    def test_bare_fileset_uses_adapter_workspace(self, controller, tmp_path):
        """A bare ``fileset`` (no ``"{ws}/"`` prefix) is anchored on the *adapter's* workspace.

        The fileset was uploaded by whoever created the adapter, so it lives in the
        adapter's own workspace — not the base model's. Using the base model's workspace
        here would silently fetch the wrong fileset (or 404) whenever the adapter and
        base model live in different workspaces.
        """
        adapter = _make_adapter("my-adapter", "fileset-only", updated_at=None, workspace="adapter-ws")
        dir_name = "adapter-ws--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        controller._download_adapter(adapter_dir, adapter, "adapter-ws")

        controller._sdk.files.list.assert_called_once_with(workspace="adapter-ws", fileset="fileset-only")
        controller._sdk.files.download.assert_called_once_with(
            fileset="fileset-only", workspace="adapter-ws", local_path=unittest.mock.ANY
        )

    def test_qualified_fileset_overrides_adapter_workspace(self, controller, tmp_path):
        """A ``"{ws}/{name}"`` fileset reference uses the qualifier verbatim.

        Even when the adapter lives in ``adapter-ws``, an explicit ``other-ws/fs`` reference
        means the fileset was uploaded under ``other-ws`` and must be fetched there.
        """
        adapter = _make_adapter("my-adapter", "other-ws/shared-fs", updated_at=None, workspace="adapter-ws")
        dir_name = "adapter-ws--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        controller._download_adapter(adapter_dir, adapter, "adapter-ws")

        controller._sdk.files.list.assert_called_once_with(workspace="other-ws", fileset="shared-fs")
        controller._sdk.files.download.assert_called_once_with(
            fileset="shared-fs", workspace="other-ws", local_path=unittest.mock.ANY
        )

    def test_temp_dir_uses_dir_name_not_adapter_name(self, controller, tmp_path):
        """Concurrent same-name adapters in different workspaces must not collide on the temp dir.

        The staging directory name must derive from the composite ``dir_name`` so that
        ``ws-a--my-adapter`` and ``ws-b--my-adapter`` materialize through distinct
        ``.ws-a--my-adapter.tmp`` / ``.ws-b--my-adapter.tmp`` paths rather than racing on
        a single ``.my-adapter.tmp``.
        """
        adapter = _make_adapter("my-adapter", "ws-a/fs", updated_at=None, workspace="ws-a")
        dir_name = "ws-a--my-adapter"
        adapter_dir = str(tmp_path / dir_name)

        captured_paths: list[str] = []

        def _capture_local_path(*, fileset, workspace, local_path):
            captured_paths.append(local_path)

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response
        controller._sdk.files.download.side_effect = _capture_local_path

        controller._download_adapter(adapter_dir, adapter, "ws-a")

        assert len(captured_paths) == 1
        assert os.path.basename(captured_paths[0]) == f".{dir_name}.tmp"


class TestRewriteAdapterBaseModel:
    """Tests for the vLLM base_model_name_or_path rewrite on downloaded adapters."""

    def test_rewrite_replaces_base_model_name(self, controller, tmp_path):
        controller.base_model_name_override = "/model-store"
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps({"peft_type": "LORA", "base_model_name_or_path": "Qwen/Qwen2.5-1.5B-Instruct", "r": 8})
        )

        assert controller._rewrite_adapter_base_model(str(adapter_dir)) is True

        cfg = json.loads((adapter_dir / "adapter_config.json").read_text())
        assert cfg["base_model_name_or_path"] == "/model-store"
        # Other fields are preserved.
        assert cfg["peft_type"] == "LORA"
        assert cfg["r"] == 8

    def test_rewrite_missing_config_returns_false(self, controller, tmp_path):
        controller.base_model_name_override = "/model-store"
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        # No adapter_config.json present -> returns False (not publishable), no raise.
        assert controller._rewrite_adapter_base_model(str(adapter_dir)) is False
        assert not (adapter_dir / "adapter_config.json").exists()

    def test_download_rewrites_when_override_set(self, controller, tmp_path):
        """_download_adapter rewrites the base model name when the override is set."""
        controller.base_model_name_override = "/model-store"
        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None, workspace="ws")
        adapter_dir = str(tmp_path / "ws--my-adapter")

        def fake_download(dest_dir, workspace, name):
            with open(os.path.join(dest_dir, "adapter_config.json"), "w") as f:
                json.dump({"peft_type": "LORA", "base_model_name_or_path": "Qwen/Qwen2.5-1.5B-Instruct"}, f)
            return True

        with patch.object(controller, "download_fileset", side_effect=fake_download):
            controller._download_adapter(adapter_dir, adapter, "ws")

        with open(os.path.join(adapter_dir, "adapter_config.json")) as f:
            cfg = json.load(f)
        assert cfg["base_model_name_or_path"] == "/model-store"

    def test_download_does_not_rewrite_when_override_empty(self, controller, tmp_path):
        """When the override is empty (NIM), the adapter config is left untouched."""
        controller.base_model_name_override = ""
        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None, workspace="ws")
        adapter_dir = str(tmp_path / "ws--my-adapter")

        def fake_download(dest_dir, workspace, name):
            with open(os.path.join(dest_dir, "adapter_config.json"), "w") as f:
                json.dump({"peft_type": "LORA", "base_model_name_or_path": "Qwen/Qwen2.5-1.5B-Instruct"}, f)
            return True

        with patch.object(controller, "download_fileset", side_effect=fake_download):
            controller._download_adapter(adapter_dir, adapter, "ws")

        with open(os.path.join(adapter_dir, "adapter_config.json")) as f:
            cfg = json.load(f)
        assert cfg["base_model_name_or_path"] == "Qwen/Qwen2.5-1.5B-Instruct"

    def test_download_does_not_publish_when_rewrite_fails(self, controller, tmp_path):
        """When the override is set but the rewrite fails (e.g. missing adapter_config.json),
        the adapter must NOT be published: it would never auto-resolve in vLLM. The temp dir
        is cleaned up and the adapter dir is not created, so it retries next cycle."""
        controller.base_model_name_override = "/model-store"
        adapter = _make_adapter("my-adapter", "ws/fileset-v1", updated_at=None, workspace="ws")
        adapter_dir = str(tmp_path / "ws--my-adapter")

        # Download succeeds but produces no adapter_config.json -> rewrite returns False.
        def fake_download(dest_dir, workspace, name):
            with open(os.path.join(dest_dir, "weights.bin"), "w") as f:
                f.write("weights")
            return True

        with patch.object(controller, "download_fileset", side_effect=fake_download):
            with pytest.raises(RuntimeError, match="refusing to publish"):
                controller._download_adapter(adapter_dir, adapter, "ws")

        # Adapter dir not published; no orphaned temp dirs left behind.
        assert not os.path.exists(adapter_dir)
        temp_dirs = [e for e in os.listdir(tmp_path) if e.startswith(".")]
        assert temp_dirs == []


class TestUpdateLoraAdaptersRedownload:
    """Tests for _update_lora_adapters re-download on fileset change."""

    def test_redownloads_when_fileset_changes(self, controller, tmp_path):
        """Verify that an adapter whose fileset changed is re-downloaded."""
        dir_name = "default--my-adapter"
        adapter_dir = tmp_path / dir_name
        adapter_dir.mkdir()
        old_meta = {"fileset": "default/old-fileset", "updated_at": None}
        with open(adapter_dir / ADAPTER_META_FILENAME, "w") as f:
            json.dump(old_meta, f)
        (adapter_dir / "old_weight.bin").write_text("old data")

        ts = datetime(2026, 3, 1, tzinfo=timezone.utc)
        adapter = _make_adapter("my-adapter", "default/new-fileset", updated_at=ts)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert dir_name in dirs_to_keep
        assert not (adapter_dir / "old_weight.bin").exists()
        meta_path = adapter_dir / ADAPTER_META_FILENAME
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["fileset"] == "default/new-fileset"

    def test_skips_download_when_metadata_matches(self, controller, tmp_path):
        """Verify that an up-to-date adapter is not re-downloaded."""
        ts = datetime(2026, 1, 1, tzinfo=timezone.utc)
        dir_name = "default--my-adapter"
        adapter_dir = tmp_path / dir_name
        adapter_dir.mkdir()
        meta = {"fileset": "default/same-fileset", "updated_at": ts.isoformat()}
        with open(adapter_dir / ADAPTER_META_FILENAME, "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("my-adapter", "default/same-fileset", updated_at=ts)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert dir_name in dirs_to_keep
        controller._sdk.files.list.assert_not_called()
        controller._sdk.files.download.assert_not_called()

    def test_downloads_new_adapter(self, controller, tmp_path):
        """Verify that a brand-new adapter (no directory) is downloaded with metadata."""
        ts = datetime(2026, 2, 1, tzinfo=timezone.utc)
        adapter = _make_adapter("new-adapter", "default/fileset-a", updated_at=ts)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        dir_name = "default--new-adapter"
        assert dir_name in dirs_to_keep
        adapter_dir = tmp_path / dir_name
        assert adapter_dir.is_dir()
        controller._sdk.files.download.assert_called_once()

        meta_path = adapter_dir / ADAPTER_META_FILENAME
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["fileset"] == "default/fileset-a"
        assert meta["updated_at"] == ts.isoformat()

    def test_no_orphaned_temp_dirs_after_download(self, controller, tmp_path):
        """Verify that no temporary directories remain after a successful download."""
        adapter = _make_adapter("clean-adapter", "default/fileset-b", updated_at=None)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        entries = os.listdir(tmp_path)
        temp_dirs = [e for e in entries if e.startswith(".")]
        assert temp_dirs == [], f"Orphaned temp dirs found: {temp_dirs}"
        assert "default--clean-adapter" in entries

    def test_failed_download_leaves_no_adapter_dir(self, controller, tmp_path):
        """Verify that a failed download cleans up the temp dir and creates no adapter dir."""
        adapter = _make_adapter("fail-adapter", "default/missing-fileset", updated_at=None)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = []
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert not (tmp_path / "default--fail-adapter").exists()
        entries = os.listdir(tmp_path)
        temp_dirs = [e for e in entries if e.startswith(".")]
        assert temp_dirs == [], f"Orphaned temp dirs found: {temp_dirs}"

    def test_failed_download_preserves_old_adapter(self, controller, tmp_path):
        """Verify that a failed re-download leaves the old adapter intact."""
        dir_name = "default--my-adapter"
        adapter_dir = tmp_path / dir_name
        adapter_dir.mkdir()
        old_meta = {"fileset": "default/old-fileset", "updated_at": None}
        with open(adapter_dir / ADAPTER_META_FILENAME, "w") as f:
            json.dump(old_meta, f)
        (adapter_dir / "weight.bin").write_text("old weights")

        adapter = _make_adapter("my-adapter", "default/new-fileset", updated_at=None)

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "default"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = []
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert (adapter_dir / "weight.bin").read_text() == "old weights"
        with open(adapter_dir / ADAPTER_META_FILENAME) as f:
            meta = json.load(f)
        assert meta["fileset"] == "default/old-fileset"

        temp_dirs = [e for e in os.listdir(tmp_path) if e.startswith(".")]
        assert temp_dirs == []


class TestUpdateLoraAdaptersCrossWorkspace:
    """Tests for the new ``{adapter_ws}--{adapter_name}`` on-disk encoding (AALGO-129)."""

    def test_two_adapters_same_name_different_workspaces_coexist(self, controller, tmp_path):
        """Two adapters sharing ``adapter.name`` but in different workspaces materialize to distinct dirs."""
        adapter_a = _make_adapter("my-adapter", "ws-a/fileset-a", updated_at=None, workspace="ws-a")
        adapter_b = _make_adapter("my-adapter", "ws-b/fileset-b", updated_at=None, workspace="ws-b")

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter_a, adapter_b]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert dirs_to_keep == {"ws-a--my-adapter", "ws-b--my-adapter"}
        assert (tmp_path / "ws-a--my-adapter").is_dir()
        assert (tmp_path / "ws-b--my-adapter").is_dir()
        assert (tmp_path / "ws-a--my-adapter" / ADAPTER_META_FILENAME).exists()
        assert (tmp_path / "ws-b--my-adapter" / ADAPTER_META_FILENAME).exists()

    def test_dir_name_uses_adapter_workspace_not_base_model_workspace(self, controller, tmp_path):
        """Cross-workspace adapter (lives in ``adapter-ws``, base model in ``base-ws``) uses adapter workspace."""
        adapter = _make_adapter("cross-ws-adapter", "adapter-ws/fs", updated_at=None, workspace="adapter-ws")

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert "adapter-ws--cross-ws-adapter" in dirs_to_keep
        assert (tmp_path / "adapter-ws--cross-ws-adapter").is_dir()
        # The bare-name and base-workspace-prefixed paths must NOT be created.
        assert not (tmp_path / "cross-ws-adapter").exists()
        assert not (tmp_path / "base-ws--cross-ws-adapter").exists()

    def test_bare_fileset_for_cross_workspace_adapter_fetches_from_adapter_workspace(self, controller, tmp_path):
        """End-to-end: a bare ``fileset`` on a cross-workspace adapter fetches from the
        adapter's workspace, not the base model's.

        This pins the wiring in ``_update_lora_adapters`` that propagates the resolved
        ``adapter_workspace`` (not ``model_entity.workspace``) into ``_download_adapter``,
        so the bare-fileset rule inside ``_download_adapter`` anchors on the correct
        workspace. Regressing this — e.g. by passing ``model_entity.workspace`` here —
        would silently 404 fileset fetches whenever the adapter and base model live in
        different workspaces.
        """
        adapter = _make_adapter(
            "cross-ws-adapter",
            fileset="bare-fs",
            updated_at=None,
            workspace="adapter-ws",
        )
        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        controller._update_lora_adapters(set())

        controller._sdk.files.list.assert_called_once_with(workspace="adapter-ws", fileset="bare-fs")
        controller._sdk.files.download.assert_called_once_with(
            fileset="bare-fs", workspace="adapter-ws", local_path=unittest.mock.ANY
        )

    def test_step_gc_removes_stale_dir_after_adapter_workspace_change(self, controller, tmp_path):
        """``step()``'s GC pass removes a stale ``{ws_old}--{name}`` dir after the adapter is moved.

        Simulates an adapter being deleted from workspace ``ws-old`` and re-created in workspace
        ``ws-new`` with the same name. The ``ws-old--my-adapter`` dir must be reaped on the next
        sync, leaving only ``ws-new--my-adapter``.
        """
        stale_dir = tmp_path / "ws-old--my-adapter"
        stale_dir.mkdir()
        (stale_dir / ADAPTER_META_FILENAME).write_text(json.dumps({"fileset": "ws-old/fs", "updated_at": None}))

        adapter = _make_adapter("my-adapter", "ws-new/fs", updated_at=None, workspace="ws-new")
        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        # No prompt-tuned models in this scenario.
        controller._sdk.models.list.return_value = []

        controller.step()

        entries = set(os.listdir(tmp_path))
        assert "ws-new--my-adapter" in entries
        assert "ws-old--my-adapter" not in entries

    def test_adapter_changed_meta_check_works_against_new_dir_path(self, controller, tmp_path):
        """``_adapter_changed`` must read metadata from the new ``{ws}--{name}`` path."""
        ts = datetime(2026, 5, 1, tzinfo=timezone.utc)
        dir_name = "ws-x--shared-adapter"
        adapter_dir = tmp_path / dir_name
        adapter_dir.mkdir()
        meta = {"fileset": "ws-x/fs-v1", "updated_at": ts.isoformat()}
        with open(adapter_dir / ADAPTER_META_FILENAME, "w") as f:
            json.dump(meta, f)

        adapter = _make_adapter("shared-adapter", "ws-x/fs-v1", updated_at=ts, workspace="ws-x")
        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert dir_name in dirs_to_keep
        controller._sdk.files.list.assert_not_called()
        controller._sdk.files.download.assert_not_called()


class TestResolveAdapterWorkspaceFallback:
    """Tests for the temporary ``Adapter.workspace`` SDK-schema gap.

    AALGO-117 introduces first-class :class:`Adapter` entities with their own
    ``workspace`` in the entity store, but at the time of writing the public
    SDK ``Adapter`` schema does not yet expose the field. AALGO-129 needs the
    adapter workspace to encode the directory layout, so the sidecar falls
    back to the base model's workspace until the SDK schema gains
    ``workspace``. These tests pin both halves of that contract: the fallback
    must engage on the current SDK shape, and the real value must take over
    the moment the field becomes readable.
    """

    def test_fallback_uses_base_model_workspace_when_attribute_missing(self):
        """Bare object with no ``workspace`` attribute: fall back to the base model workspace."""

        class _AdapterWithoutWorkspace:
            name = "my-adapter"

        adapter = _AdapterWithoutWorkspace()
        assert AdaptersController._resolve_adapter_workspace(adapter, "base-ws") == "base-ws"

    def test_fallback_uses_base_model_workspace_when_attribute_is_none(self):
        """``workspace=None`` (e.g. older payload deserialized via Optional[str]): fall back too."""
        adapter = MagicMock()
        adapter.workspace = None
        assert AdaptersController._resolve_adapter_workspace(adapter, "base-ws") == "base-ws"

    def test_fallback_uses_base_model_workspace_when_attribute_is_empty_string(self):
        """``workspace=""`` is treated identically to ``None`` — an empty string can never form a valid
        ``{ws}--{name}`` directory anchor, so the safest behavior is the same fallback as for ``None``.
        """
        adapter = MagicMock()
        adapter.workspace = ""
        assert AdaptersController._resolve_adapter_workspace(adapter, "base-ws") == "base-ws"

    def test_explicit_workspace_takes_priority_over_base_model(self):
        """Once the SDK schema exposes ``workspace``, the real value must be used verbatim."""
        adapter = MagicMock()
        adapter.workspace = "adapter-ws"
        assert AdaptersController._resolve_adapter_workspace(adapter, "base-ws") == "adapter-ws"

    def test_update_lora_adapters_falls_back_to_base_model_workspace(self, controller, tmp_path):
        """End-to-end fallback path: an SDK Adapter without ``workspace`` is laid down under
        ``{base_model_workspace}--{adapter_name}`` so the wire format stays decodable.
        """

        class _LegacyAdapter:
            def __init__(self, name: str, fileset: str):
                self.name = name
                self.fileset = fileset
                self.enabled = True
                self.updated_at = None

        adapter = _LegacyAdapter("legacy-adapter", "base-ws/fs")

        mock_model_entity = MagicMock()
        mock_model_entity.workspace = "base-ws"
        mock_model_entity.adapters = [adapter]
        controller._sdk.models.retrieve.return_value = mock_model_entity

        mock_files_response = MagicMock()
        mock_files_response.data = [MagicMock()]
        controller._sdk.files.list.return_value = mock_files_response

        dirs_to_keep: set[str] = set()
        controller._update_lora_adapters(dirs_to_keep)

        assert dirs_to_keep == {"base-ws--legacy-adapter"}
        assert (tmp_path / "base-ws--legacy-adapter").is_dir()
