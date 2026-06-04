# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the file_io callbacks."""

import threading
from pathlib import Path

import pytest
from fsspec.callbacks import Callback
from nmp.common.jobs.schemas import PlatformJobStatus
from nmp.customizer.app.jobs.file_io.schemas import DownloadStats, TaskPhase, UploadStats
from nmp.customizer.shared.tasks.file_io.callbacks import (
    BaseProgressCallback,
    CompositeCallback,
    FileDownloadProgressCallback,
    FileUploadProgressCallback,
    SingleFileDownloadCallback,
    SingleFileUploadCallback,
    TqdmPerFileDownloadCallback,
    TqdmPerFileUploadCallback,
    get_percentage,
)
from pytest_mock import MockerFixture

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_progress_reporter(mocker: MockerFixture):
    """Create a mock ProgressReporter."""
    reporter = mocker.Mock()
    reporter.update_progress = mocker.Mock()
    return reporter


@pytest.fixture
def upload_stats() -> UploadStats:
    """Create a fresh UploadStats instance."""
    return UploadStats()


@pytest.fixture
def download_stats() -> DownloadStats:
    """Create a fresh DownloadStats instance."""
    return DownloadStats()


@pytest.fixture
def temp_file(tmp_path: Path) -> Path:
    """Create a temporary file with content."""
    file = tmp_path / "test_file.txt"
    file.write_text("Hello, World!")
    return file


@pytest.fixture
def temp_directory(tmp_path: Path) -> Path:
    """Create a temporary directory with multiple files."""
    dir_path = tmp_path / "test_dir"
    dir_path.mkdir()
    (dir_path / "file1.txt").write_text("Content 1")
    (dir_path / "file2.txt").write_text("Content 2 longer")
    subdir = dir_path / "subdir"
    subdir.mkdir()
    (subdir / "file3.txt").write_text("Content 3 even longer")
    return dir_path


@pytest.fixture
def mock_callback(mocker: MockerFixture) -> Callback:
    """Create a mock fsspec Callback."""
    callback = mocker.Mock(spec=Callback)
    callback.branched = mocker.Mock(return_value=mocker.Mock(spec=Callback))
    return callback


@pytest.fixture
def mock_tqdm_callback(mocker: MockerFixture):
    """Mock TqdmCallback to avoid actual tqdm instances during tests."""
    return mocker.patch("nmp.customizer.shared.tasks.file_io.callbacks.TqdmCallback", autospec=True)


# ============================================================================
# TestGetPercentage
# ============================================================================


class TestGetPercentage:
    """Tests for get_percentage function."""

    @pytest.mark.parametrize(
        ("current", "total", "expected"),
        [
            (0, 100, 0),
            (100, 100, 100),
            (1, 100, 1),
            (99, 100, 99),
            (1, 3, 33),
            (2, 3, 66),
            (1, 1, 100),
            (0, 1, 0),
            (0, 0, 0),
        ],
        ids=[
            "zero_current",
            "complete",
            "one_percent",
            "ninety_nine_percent",
            "one_third_truncated",
            "two_thirds_truncated",
            "one_of_one",
            "zero_of_one",
            "zero_of_zero",
        ],
    )
    def test_get_percentage_valid_values(self, current: int, total: int, expected: int):
        """Should return correct percentage for valid inputs."""
        assert get_percentage(current, total) == expected

    @pytest.mark.parametrize(
        ("current", "total", "error_match"),
        [
            (101, 100, "current=101 cannot be greater than total=100"),
            (5, 3, "current=5 cannot be greater than total=3"),
            (-1, 100, "Unexpected negative value of the current value: current=-1"),
            (-10, 50, "Unexpected negative value of the current value: current=-10"),
            (-2, -1, "Unexpected negative value of the total value: total=-1, current=-2"),
        ],
        ids=[
            "current_exceeds_total",
            "current_greater_than_total_small",
            "negative_current",
            "negative_current_large",
            "negative_total",
        ],
    )
    def test_get_percentage_raises_on_invalid_values(self, current: int, total: int, error_match: str):
        """Should raise ValueError for invalid inputs."""
        with pytest.raises(ValueError, match=error_match):
            get_percentage(current, total)


# ============================================================================
# TestTqdmPerFileUploadCallback
# ============================================================================
class TestTqdmPerFileUploadCallback:
    """Tests for TqdmPerFileUploadCallback."""

    def test_init_sets_src_path(self, temp_file: Path):
        """Should initialize with src_path."""
        callback = TqdmPerFileUploadCallback(src_path=temp_file)
        assert callback.src_path == temp_file

    def test_branched_returns_tqdm_callback_for_file(self, temp_file: Path, mock_tqdm_callback):
        """Should return TqdmCallback with filename in description for file upload."""
        callback = TqdmPerFileUploadCallback(src_path=temp_file)
        callback.branched(str(temp_file), "dest/test_file.txt")

        mock_tqdm_callback.assert_called_once_with(
            tqdm_kwargs={
                "desc": f"Uploading {temp_file.name}",
                "unit": "B",
                "unit_scale": True,
                "unit_divisor": 1024,
                "miniters": 1,
            },
        )

    def test_branched_returns_tqdm_callback_for_directory(self, temp_directory: Path, mock_tqdm_callback):
        """Should return TqdmCallback with relative path in description for directory upload."""
        callback = TqdmPerFileUploadCallback(src_path=temp_directory)
        full_src_path = temp_directory / "subdir" / "file3.txt"
        callback.branched(str(full_src_path), "dest/subdir/file3.txt")

        mock_tqdm_callback.assert_called_once()
        call_kwargs = mock_tqdm_callback.call_args.kwargs
        assert call_kwargs["tqdm_kwargs"]["desc"] == "Uploading subdir/file3.txt"


# ============================================================================
# TestTqdmPerFileDownloadCallback
# ============================================================================


class TestTqdmPerFileDownloadCallback:
    """Tests for TqdmPerFileDownloadCallback."""

    def test_init_sets_attributes(self, tmp_path: Path):
        """Should initialize with all required attributes."""
        file_sizes = {"file1.txt": 100, "file2.txt": 200}
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
            file_sizes=file_sizes,
        )
        assert callback.dest_path == tmp_path
        assert callback.fileset_path == "workspace/fileset"
        assert callback.file_sizes == file_sizes

    def test_init_strips_trailing_slash_from_fileset_path(self, tmp_path: Path):
        """Should strip trailing slash from fileset_path."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset/",
        )
        assert callback.fileset_path == "workspace/fileset"

    def test_init_with_no_file_sizes_defaults_to_empty_dict(self, tmp_path: Path):
        """Should default file_sizes to empty dict if not provided."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
        )
        assert callback.file_sizes == {}

    def test_branched_returns_tqdm_callback_for_directory_dest(self, tmp_path: Path, mock_tqdm_callback):
        """Should return TqdmCallback with relative path in description."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
        )
        full_dest_path = tmp_path / "subdir" / "file.txt"
        callback.branched("workspace/fileset/subdir/file.txt", str(full_dest_path))

        mock_tqdm_callback.assert_called_once()
        call_kwargs = mock_tqdm_callback.call_args.kwargs
        assert call_kwargs["tqdm_kwargs"]["desc"] == "Downloading subdir/file.txt"

    def test_branched_returns_tqdm_callback_for_file_dest(self, temp_file: Path, mock_tqdm_callback):
        """Should return TqdmCallback with filename when dest is a file."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=temp_file,
            fileset_path="workspace/fileset",
        )
        callback.branched("workspace/fileset/file.txt", str(temp_file))

        mock_tqdm_callback.assert_called_once()
        call_kwargs = mock_tqdm_callback.call_args.kwargs
        assert call_kwargs["tqdm_kwargs"]["desc"] == f"Downloading {temp_file.name}"

    def test_branched_sets_size_when_file_size_known(self, tmp_path: Path, mock_tqdm_callback):
        """Should call set_size on child callback when file size is known."""
        file_sizes = {"subdir/file.txt": 12345}
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
            file_sizes=file_sizes,
        )
        full_dest_path = tmp_path / "subdir" / "file.txt"

        callback.branched("workspace/fileset/subdir/file.txt", str(full_dest_path))
        mock_tqdm_callback.return_value.set_size.assert_called_once_with(12345)

    def test_branched_does_not_set_size_when_file_size_unknown(self, tmp_path: Path, mock_tqdm_callback):
        """Should not call set_size when file size is not in file_sizes dict."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
            file_sizes={},
        )
        full_dest_path = tmp_path / "unknown.txt"

        callback.branched("workspace/fileset/unknown.txt", str(full_dest_path))
        mock_tqdm_callback.return_value.set_size.assert_not_called()

    def test_branched_handles_path_not_starting_with_fileset(self, tmp_path: Path, mock_tqdm_callback):
        """Should handle source paths that don't start with fileset_path."""
        file_sizes = {"other/path/file.txt": 999}
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path,
            fileset_path="workspace/fileset",
            file_sizes=file_sizes,
        )
        callback.branched("other/path/file.txt", str(tmp_path / "file.txt"))

        # Should still create callback
        mock_tqdm_callback.assert_called_once()
        # set_size should be called since the path matches file_sizes key exactly
        mock_tqdm_callback.return_value.set_size.assert_called_once_with(999)

    def test_branched_handles_unrelated_dest_path(self, tmp_path: Path, mock_tqdm_callback):
        """Should use filename when dest_path is not parent of full_dest_path."""
        callback = TqdmPerFileDownloadCallback(
            dest_path=tmp_path / "expected",
            fileset_path="workspace/fileset",
        )
        # Different path that's not relative to dest_path
        unrelated_path = tmp_path / "other" / "file.txt"
        callback.branched("workspace/fileset/file.txt", str(unrelated_path))

        mock_tqdm_callback.assert_called_once()
        call_kwargs = mock_tqdm_callback.call_args.kwargs
        assert call_kwargs["tqdm_kwargs"]["desc"] == "Downloading file.txt"


# ============================================================================
# TestBaseProgressCallbackListLocalFiles
# ============================================================================


class TestBaseProgressCallbackListLocalFiles:
    """Tests for BaseProgressCallback.list_local_files static method."""

    def test_list_local_files_single_file(self, temp_file: Path):
        """Should return single FileInfo for a file."""
        files = BaseProgressCallback.list_local_files(temp_file)

        assert len(files) == 1
        assert files[0].path == temp_file.name
        assert files[0].size == len("Hello, World!")

    def test_list_local_files_directory(self, temp_directory: Path):
        """Should recursively list all files in directory."""
        files = BaseProgressCallback.list_local_files(temp_directory)

        assert len(files) == 3
        paths = {f.path for f in files}
        assert "file1.txt" in paths
        assert "file2.txt" in paths
        # Path separator may vary by OS, check for subdir/file3.txt
        assert any("file3.txt" in p for p in paths)

    def test_list_local_files_nonexistent_path(self, tmp_path: Path):
        """Should return empty list for nonexistent path."""
        nonexistent = tmp_path / "does_not_exist"
        files = BaseProgressCallback.list_local_files(nonexistent)

        assert files == []

    def test_list_local_files_empty_directory(self, tmp_path: Path):
        """Should return empty list for empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        files = BaseProgressCallback.list_local_files(empty_dir)

        assert files == []


# ============================================================================
# TestFileUploadProgressCallback
# ============================================================================


class TestFileUploadProgressCallback:
    """Tests for FileUploadProgressCallback."""

    def test_init_reports_initial_progress(self, mock_progress_reporter, temp_file: Path, upload_stats: UploadStats):
        """Should report initial progress on initialization."""
        callback = FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=temp_file,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )

        mock_progress_reporter.update_progress.assert_called_once_with(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.UPLOADING,
                "fileset": "workspace/fileset",
                "total_files": 1,
                "total_size": len("Hello, World!"),
                "uploaded_files": 0,
                "uploaded_bytes": 0,
            },
        )
        assert callback.total_files == 1
        assert callback.total_size == len("Hello, World!")

    def test_init_with_directory(self, mock_progress_reporter, temp_directory: Path, upload_stats: UploadStats):
        """Should compute total files and size from directory."""
        callback = FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=temp_directory,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )

        assert callback.total_files == 3

    def test_init_with_nonexistent_path(self, mock_progress_reporter, tmp_path: Path, upload_stats: UploadStats):
        """Should handle nonexistent path gracefully."""
        nonexistent = tmp_path / "does_not_exist"
        callback = FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=nonexistent,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )

        assert callback.total_files == 0
        assert callback.total_size == 0

    def test_branched_returns_single_file_upload_callback(
        self,
        mock_progress_reporter,
        temp_file: Path,
        upload_stats: UploadStats,
    ):
        """Should return SingleFileUploadCallback from branched."""
        callback = FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=temp_file,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )
        child = callback.branched("/local/path/file.txt", "workspace/fileset/file.txt")

        assert isinstance(child, SingleFileUploadCallback)
        assert child.parent is callback
        assert child.source_path == "/local/path/file.txt"
        assert child.dest_path == "workspace/fileset/file.txt"


# ============================================================================
# TestSingleFileUploadCallback
# ============================================================================


class TestSingleFileUploadCallback:
    """Tests for SingleFileUploadCallback."""

    @pytest.fixture
    def parent_callback(self, mock_progress_reporter, temp_file: Path, upload_stats: UploadStats):
        """Create a parent FileUploadProgressCallback."""
        return FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=temp_file,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )

    @pytest.fixture
    def single_file_callback(self, parent_callback: FileUploadProgressCallback) -> SingleFileUploadCallback:
        """Create a SingleFileUploadCallback."""
        return SingleFileUploadCallback(
            parent=parent_callback,
            source_path="/local/path/file.txt",
            dest_path="workspace/fileset/subdir/file.txt",
        )

    def test_get_phase_returns_uploading(self, single_file_callback: SingleFileUploadCallback):
        """Should return TaskPhase.UPLOADING."""
        assert single_file_callback._get_phase() == TaskPhase.UPLOADING

    def test_get_file_display_path_returns_filename(self, single_file_callback: SingleFileUploadCallback):
        """Should extract filename from dest_path."""
        assert single_file_callback._get_file_display_path() == "file.txt"

    def test_get_file_display_path_handles_no_slash(self, parent_callback: FileUploadProgressCallback):
        """Should return dest_path as-is if no slash."""
        callback = SingleFileUploadCallback(
            parent=parent_callback,
            source_path="/local/file.txt",
            dest_path="file.txt",
        )
        assert callback._get_file_display_path() == "file.txt"

    def test_update_stats_increments_files_uploaded(self, single_file_callback: SingleFileUploadCallback):
        """Should increment files_uploaded counter."""
        assert single_file_callback.parent.stats.files_uploaded == 0
        single_file_callback._update_stats()
        assert single_file_callback.parent.stats.files_uploaded == 1

    def test_update_stats_adds_size_when_set(self, single_file_callback: SingleFileUploadCallback):
        """Should add size to total_bytes when size is set."""
        single_file_callback.size = 12345
        single_file_callback._update_stats()
        assert single_file_callback.parent.stats.total_bytes == 12345

    def test_update_stats_no_size_when_none(self, single_file_callback: SingleFileUploadCallback):
        """Should not add to total_bytes when size is None."""
        single_file_callback.size = None
        single_file_callback._update_stats()
        assert single_file_callback.parent.stats.total_bytes == 0

    def test_get_files_count_returns_uploaded_count(self, single_file_callback: SingleFileUploadCallback):
        """Should return current files_uploaded count."""
        single_file_callback.parent.stats.files_uploaded = 5
        assert single_file_callback._get_files_count() == 5

    def test_build_status_details_returns_upload_details(self, single_file_callback: SingleFileUploadCallback):
        """Should build correct status details dict."""
        single_file_callback.parent.total_files = 2
        details = single_file_callback._build_status_details(
            files_count=2,
            total_bytes=1024,
            current_file="test.txt",
        )

        assert details == {
            "phase": TaskPhase.UPLOADING,
            "fileset": "workspace/fileset",
            "total_files": 2,
            "total_size": len("Hello, World!"),
            "uploaded_files": 2,
            "uploaded_bytes": 1024,
            "current_file": "test.txt",
            "progress_pct": 100,
        }

    def test_close_updates_stats_and_reports_progress(
        self,
        single_file_callback: SingleFileUploadCallback,
        mock_progress_reporter,
    ):
        """Should update stats and call progress reporter on close."""
        single_file_callback.size = 1000
        mock_progress_reporter.reset_mock()

        single_file_callback.close()

        assert single_file_callback.parent.stats.files_uploaded == 1
        assert single_file_callback.parent.stats.total_bytes == 1000
        mock_progress_reporter.update_progress.assert_called_once()

    def test_close_is_idempotent(self, single_file_callback: SingleFileUploadCallback, mock_progress_reporter):
        """Should only process close once."""
        mock_progress_reporter.reset_mock()

        single_file_callback.close()
        single_file_callback.close()

        assert single_file_callback.parent.stats.files_uploaded == 1
        mock_progress_reporter.update_progress.assert_called_once()

    def test_context_manager_calls_close(self, single_file_callback: SingleFileUploadCallback, mock_progress_reporter):
        """Should call close when used as context manager."""
        mock_progress_reporter.reset_mock()

        with single_file_callback:
            pass

        mock_progress_reporter.update_progress.assert_called_once()


# ============================================================================
# TestFileDownloadProgressCallback
# ============================================================================


class TestFileDownloadProgressCallback:
    """Tests for FileDownloadProgressCallback."""

    def test_init_reports_initial_progress(self, mock_progress_reporter, download_stats: DownloadStats):
        """Should report initial progress on initialization."""
        callback = FileDownloadProgressCallback(
            progress_reporter=mock_progress_reporter,
            fileset_name="workspace/fileset",
            total_files=10,
            total_size=5000,
            stats=download_stats,
        )

        mock_progress_reporter.update_progress.assert_called_once_with(
            status=PlatformJobStatus.ACTIVE,
            status_details={
                "phase": TaskPhase.DOWNLOADING,
                "fileset": "workspace/fileset",
                "total_files": 10,
                "total_size": 5000,
                "downloaded_files": 0,
                "downloaded_bytes": 0,
            },
        )
        assert callback.total_files == 10
        assert callback.total_size == 5000

    def test_branched_returns_single_file_download_callback(
        self,
        mock_progress_reporter,
        download_stats: DownloadStats,
    ):
        """Should return SingleFileDownloadCallback from branched."""
        callback = FileDownloadProgressCallback(
            progress_reporter=mock_progress_reporter,
            fileset_name="workspace/fileset",
            total_files=10,
            total_size=5000,
            stats=download_stats,
        )
        child = callback.branched("workspace/fileset/file.txt", "/local/path/file.txt")

        assert isinstance(child, SingleFileDownloadCallback)
        assert child.parent is callback
        assert child.source_path == "workspace/fileset/file.txt"
        assert child.dest_path == "/local/path/file.txt"


# ============================================================================
# TestSingleFileDownloadCallback
# ============================================================================


class TestSingleFileDownloadCallback:
    """Tests for SingleFileDownloadCallback."""

    @pytest.fixture
    def parent_callback(self, mock_progress_reporter, download_stats: DownloadStats):
        """Create a parent FileDownloadProgressCallback."""
        return FileDownloadProgressCallback(
            progress_reporter=mock_progress_reporter,
            fileset_name="workspace/fileset",
            total_files=10,
            total_size=5000,
            stats=download_stats,
        )

    @pytest.fixture
    def single_file_callback(self, parent_callback: FileDownloadProgressCallback) -> SingleFileDownloadCallback:
        """Create a SingleFileDownloadCallback."""
        return SingleFileDownloadCallback(
            parent=parent_callback,
            source_path="workspace/fileset/subdir/file.txt",
            dest_path="/local/path/file.txt",
        )

    def test_get_phase_returns_downloading(self, single_file_callback: SingleFileDownloadCallback):
        """Should return TaskPhase.DOWNLOADING."""
        assert single_file_callback._get_phase() == TaskPhase.DOWNLOADING

    def test_get_file_display_path_returns_filename(self, single_file_callback: SingleFileDownloadCallback):
        """Should extract filename from source_path."""
        assert single_file_callback._get_file_display_path() == "file.txt"

    def test_get_file_display_path_handles_no_slash(self, parent_callback: FileDownloadProgressCallback):
        """Should return source_path as-is if no slash."""
        callback = SingleFileDownloadCallback(
            parent=parent_callback,
            source_path="file.txt",
            dest_path="/local/file.txt",
        )
        assert callback._get_file_display_path() == "file.txt"

    def test_update_stats_increments_files_downloaded(self, single_file_callback: SingleFileDownloadCallback):
        """Should increment files_downloaded counter."""
        assert single_file_callback.parent.stats.files_downloaded == 0
        single_file_callback._update_stats()
        assert single_file_callback.parent.stats.files_downloaded == 1

    def test_update_stats_adds_size_when_set(self, single_file_callback: SingleFileDownloadCallback):
        """Should add size to total_bytes when size is set."""
        single_file_callback.size = 54321
        single_file_callback._update_stats()
        assert single_file_callback.parent.stats.total_bytes == 54321

    def test_get_files_count_returns_downloaded_count(self, single_file_callback: SingleFileDownloadCallback):
        """Should return current files_downloaded count."""
        single_file_callback.parent.stats.files_downloaded = 7
        assert single_file_callback._get_files_count() == 7

    def test_build_status_details_returns_download_details(self, single_file_callback: SingleFileDownloadCallback):
        """Should build correct status details dict."""
        details = single_file_callback._build_status_details(
            files_count=3,
            total_bytes=2048,
            current_file="data.bin",
        )

        assert details == {
            "phase": TaskPhase.DOWNLOADING,
            "fileset": "workspace/fileset",
            "total_files": 10,
            "total_size": 5000,
            "downloaded_files": 3,
            "downloaded_bytes": 2048,
            "current_file": "data.bin",
            "progress_pct": 30,  # 3/10 = 30%
        }

    def test_close_updates_stats_and_reports_progress(
        self,
        single_file_callback: SingleFileDownloadCallback,
        mock_progress_reporter,
    ):
        """Should update stats and call progress reporter on close."""
        single_file_callback.size = 500
        mock_progress_reporter.reset_mock()

        single_file_callback.close()

        assert single_file_callback.parent.stats.files_downloaded == 1
        assert single_file_callback.parent.stats.total_bytes == 500
        mock_progress_reporter.update_progress.assert_called_once()


# ============================================================================
# TestCompositeCallback
# ============================================================================


class TestCompositeCallback:
    """Tests for CompositeCallback."""

    def test_init_stores_callbacks(self, mock_callback: Callback, mocker: MockerFixture):
        """Should store all provided callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)

        assert composite.callbacks == [cb1, cb2]

    def test_init_with_no_callbacks(self):
        """Should work with no callbacks."""
        composite = CompositeCallback()
        assert composite.callbacks == []

    def test_set_size_propagates_to_all_callbacks(self, mocker: MockerFixture):
        """Should call set_size on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)

        composite.set_size(1000)

        assert composite.size == 1000
        cb1.set_size.assert_called_once_with(1000)
        cb2.set_size.assert_called_once_with(1000)

    def test_absolute_update_propagates_to_all_callbacks(self, mocker: MockerFixture):
        """Should call absolute_update on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)

        composite.absolute_update(500)

        assert composite.value == 500
        cb1.absolute_update.assert_called_once_with(500)
        cb2.absolute_update.assert_called_once_with(500)

    def test_relative_update_propagates_to_all_callbacks(self, mocker: MockerFixture):
        """Should call relative_update on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)
        composite.value = 100

        composite.relative_update(50)

        assert composite.value == 150
        cb1.relative_update.assert_called_once_with(50)
        cb2.relative_update.assert_called_once_with(50)

    def test_relative_update_default_increment(self, mocker: MockerFixture):
        """Should default to increment of 1."""
        cb1 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1)
        composite.value = 0

        composite.relative_update()

        assert composite.value == 1
        cb1.relative_update.assert_called_once_with(1)

    def test_branched_returns_composite_with_branched_children(self, mocker: MockerFixture):
        """Should return new CompositeCallback with branched children."""
        child1 = mocker.Mock(spec=Callback)
        child2 = mocker.Mock(spec=Callback)
        cb1 = mocker.Mock(spec=Callback)
        cb1.branched.return_value = child1
        cb2 = mocker.Mock(spec=Callback)
        cb2.branched.return_value = child2

        composite = CompositeCallback(cb1, cb2)
        branched = composite.branched("src/file.txt", "dest/file.txt", extra_kwarg="value")

        assert isinstance(branched, CompositeCallback)
        assert branched.callbacks == [child1, child2]
        cb1.branched.assert_called_once_with("src/file.txt", "dest/file.txt", extra_kwarg="value")
        cb2.branched.assert_called_once_with("src/file.txt", "dest/file.txt", extra_kwarg="value")

    def test_call_propagates_to_all_callbacks(self, mocker: MockerFixture):
        """Should call hook on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)

        composite.call("test_hook", arg1="value1")

        cb1.call.assert_called_once_with("test_hook", arg1="value1")
        cb2.call.assert_called_once_with("test_hook", arg1="value1")

    def test_close_closes_all_callbacks(self, mocker: MockerFixture):
        """Should call close on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb2 = mocker.Mock(spec=Callback)
        composite = CompositeCallback(cb1, cb2)

        composite.close()

        cb1.close.assert_called_once()
        cb2.close.assert_called_once()

    def test_context_manager_enters_and_exits_all_callbacks(self, mocker: MockerFixture):
        """Should call __enter__ and __exit__ on all child callbacks."""
        cb1 = mocker.Mock(spec=Callback)
        cb1.__enter__ = mocker.Mock(return_value=cb1)
        cb1.__exit__ = mocker.Mock(return_value=None)
        cb2 = mocker.Mock(spec=Callback)
        cb2.__enter__ = mocker.Mock(return_value=cb2)
        cb2.__exit__ = mocker.Mock(return_value=None)

        composite = CompositeCallback(cb1, cb2)

        with composite as ctx:
            assert ctx is composite
            cb1.__enter__.assert_called_once()
            cb2.__enter__.assert_called_once()

        cb1.__exit__.assert_called_once()
        cb2.__exit__.assert_called_once()


# ============================================================================
# Thread Safety Tests
# ============================================================================


class TestThreadSafety:
    """Tests for thread-safe behavior of callbacks."""

    def test_concurrent_close_calls_are_thread_safe(
        self,
        mock_progress_reporter,
        tmp_path: Path,
        upload_stats: UploadStats,
    ):
        """Should handle concurrent close calls without race conditions."""
        # Create a directory with 10 files to match the 10 child callbacks
        test_dir = tmp_path / "test_concurrent"
        test_dir.mkdir()
        num_files = 10
        file_size = 100
        for i in range(num_files):
            (test_dir / f"file{i}.txt").write_text(f"Content {i}")

        parent = FileUploadProgressCallback(
            progress_reporter=mock_progress_reporter,
            src_path=test_dir,
            fileset_name="workspace/fileset",
            stats=upload_stats,
        )

        # Create multiple child callbacks (one per file)
        children = [
            SingleFileUploadCallback(parent=parent, source_path=f"/path/file{i}.txt", dest_path=f"dest/file{i}.txt")
            for i in range(num_files)
        ]

        # Set sizes
        for i, child in enumerate(children):
            child.size = file_size * (i + 1)

        # Close all concurrently
        threads = [threading.Thread(target=child.close) for child in children]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all files were counted
        assert upload_stats.files_uploaded == num_files
        # Total bytes should be sum of 100, 200, ..., 1000 = 5500
        assert upload_stats.total_bytes == sum(file_size * (i + 1) for i in range(num_files))
