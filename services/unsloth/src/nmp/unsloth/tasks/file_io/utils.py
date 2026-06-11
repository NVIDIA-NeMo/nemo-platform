# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

# https://docs.nvidia.com/nemo/microservices/latest/pysdk/index.html#handling-errors
from nemo_platform import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
)
from nmp.unsloth.app.jobs.file_io.schemas import (
    FileDownloadError,
    FileIOTaskConfig,
    FileUploadError,
    PathTraversalError,
    ProgressReportError,
)

logger = logging.getLogger(__name__)


@contextmanager
def filesystem_sdk_error_handler(
    error_class: type[FileDownloadError | FileUploadError | ProgressReportError],
    operation: str,
    passthrough: tuple[type[BaseException], ...] = (),
) -> Iterator[None]:
    """Context manager for consistent FilesetFileSystem error handling.

    Catches FilesetFileSystem-specific exceptions and re-raises them as the
    specified error class with a consistent message format.
    """
    try:
        yield
    except passthrough:
        raise
    except FileNotFoundError as e:
        raise error_class(f"Failed to {operation} due to file not found error. Error: {e}") from e
    except PermissionError as e:
        raise error_class(f"Failed to {operation} due to permission denied error. Error: {e}") from e
    except httpx.TimeoutException as e:
        raise error_class(f"Failed to {operation} due to request timeout. Error: {e}") from e
    except httpx.ConnectError as e:
        raise error_class(f"Failed to {operation} due to connection error. Error: {e}") from e
    except Exception as e:
        raise error_class(f"Failed to {operation} due to unexpected error {type(e).__name__}: {e}") from e


@contextmanager
def sdk_error_handler(
    error_class: type[FileDownloadError | FileUploadError | ProgressReportError],
    operation: str,
    passthrough: tuple[type[BaseException], ...] = (),
) -> Iterator[None]:
    """Context manager for consistent SDK error handling.

    Catches SDK-specific exceptions and re-raises them as the specified error
    class with a consistent message format.
    """
    try:
        yield
    except passthrough:
        raise
    except APITimeoutError as e:
        raise error_class(
            f"Failed to {operation} due to request timeout error. Cause: {e.__cause__}. Error: {e}",
        ) from e
    except APIConnectionError as e:
        raise error_class(f"Failed to {operation} due to connection error. Cause: {e.__cause__}. Error: {e}") from e
    # AuthenticationError / PermissionDeniedError are subclasses of APIStatusError,
    # so they must be caught before APIStatusError.
    except AuthenticationError as e:
        raise error_class(f"Failed to {operation} due to authentication error. Error: {e}") from e
    except PermissionDeniedError as e:
        raise error_class(f"Failed to {operation} due to permission denied error. Error: {e}") from e
    except APIStatusError as e:
        raise error_class(f"Failed to {operation} due to API error. Status code: {e.status_code}. Error: {e}") from e
    except Exception as e:
        raise error_class(f"Failed to {operation} due to unexpected error {type(e).__name__}: {e}") from e


def get_config(config_path: Path) -> FileIOTaskConfig:
    """Load and validate the file_io step config from disk."""
    with open(config_path) as f:
        return FileIOTaskConfig.model_validate(json.load(f))


def validate_storage_path(storage_path: Path) -> Path:
    """Validate that a storage path exists and is a directory."""
    if not storage_path.exists() or not storage_path.is_dir():
        raise FileUploadError(
            f"Storage path does not exist: {storage_path}. Ensure the storage path exists and is a directory.",
        )
    return storage_path


def validate_safe_path(base_path: Path, user_path: str) -> Path:
    """Validate that a user-provided path stays within the base directory.

    Resolves both paths to canonical absolute form and verifies the result
    is under the base path. Prevents path traversal via ``..`` etc.

    Raises:
        PathTraversalError: If the resolved path would escape base_path.
    """
    resolved_base = base_path.resolve()
    resolved_path = (base_path / user_path).resolve()

    if not resolved_path.is_relative_to(resolved_base):
        raise PathTraversalError(
            f"Path '{user_path}' resolves outside of the base directory. "
            "This may indicate a path traversal attack. "
            "Ensure that paths such as ../.. are not used in the download destination path.",
        )

    return resolved_path
