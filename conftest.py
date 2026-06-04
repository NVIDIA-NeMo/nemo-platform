# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Root-level conftest.py for NeMo Platform

This file contains shared fixtures and configuration that are available to all tests
in the repository. Individual packages and services can add their own conftest.py
files for more specific fixtures.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Generator

import pytest
from nmp.testing.pytest_outcomes import pytest_skip as skip_test

from tests.discovery_exclusions import TEST_DISCOVERY_EXCLUSIONS

# Set test environment variables BEFORE any imports
# This must happen at module level, before pytest even starts processing
if "MODE" not in os.environ:
    os.environ["MODE"] = "development"

# Silence config warnings during tests - services don't need the config file
# when using create_test_client() which programmatically sets configuration overrides
if "NMP_CONFIG_WARNINGS_DISABLED" not in os.environ:
    os.environ["NMP_CONFIG_WARNINGS_DISABLED"] = "1"


# ============================================================================
# Suppress httpcore debug logging during cleanup
# This prevents "I/O operation on closed file" errors when huggingface_hub's
# atexit handler tries to log debug messages after pytest closes stdout/stderr
# ============================================================================
_httpcore_logger = logging.getLogger("httpcore")
_httpcore_logger.setLevel(logging.WARNING)
_httpcore_logger.propagate = False  # Prevent any handlers from receiving these messages

_httpx_logger = logging.getLogger("httpx")
_httpx_logger.setLevel(logging.WARNING)
_httpx_logger.propagate = False


# ============================================================================
# Session-level fixtures
# ============================================================================


@pytest.fixture(scope="session", autouse=True)
def cleanup_huggingface_hub_session():
    """
    Clean up huggingface_hub HTTP sessions before pytest shuts down.

    This prevents "I/O operation on closed file" logging errors that occur when
    huggingface_hub's atexit handler tries to close HTTP connections after
    pytest has already closed stdout/stderr.
    """
    yield
    # Suppress httpcore logging during cleanup to prevent errors on closed streams
    # This must be done again here in case new loggers were created during tests
    logging.getLogger("httpcore").setLevel(logging.CRITICAL)
    logging.getLogger("httpcore").propagate = False
    logging.getLogger("httpcore").disabled = True

    # Clean up huggingface_hub's HTTP client before pytest closes streams
    try:
        from huggingface_hub.utils import _http

        # Close the session if it exists
        if hasattr(_http, "get_session"):
            # Newer versions use get_session()
            try:
                session = _http.get_session()
                if session is not None:
                    session.close()
            except Exception:
                pass
        # Also try the module-level close function
        if hasattr(_http, "close_session"):
            try:
                _http.close_session()
            except Exception:
                pass
    except (ImportError, AttributeError):
        pass  # huggingface_hub not installed or structure changed


@pytest.fixture(scope="session")
def test_data_dir() -> Path:
    """Return the path to the test data directory."""
    return Path(__file__).parent / "tests" / "data"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Return the path to the repository root."""
    return Path(__file__).parent


# ============================================================================
# Function-level fixtures
# ============================================================================


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for a test.

    The directory is automatically cleaned up after the test completes.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_file() -> Generator[Path, None, None]:
    """
    Create a temporary file for a test.

    The file is automatically cleaned up after the test completes.
    """
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmpfile:
        tmpfile_path = Path(tmpfile.name)

    yield tmpfile_path

    # Cleanup
    if tmpfile_path.exists():
        tmpfile_path.unlink()


@pytest.fixture
def mock_env_vars(monkeypatch) -> dict:
    """
    Provide a way to set environment variables for a test.

    Usage:
        def test_something(mock_env_vars):
            mock_env_vars['MY_VAR'] = 'value'
            # Test code that reads MY_VAR
    """
    env_vars = {}

    def set_env(key: str, value: str):
        env_vars[key] = value
        monkeypatch.setenv(key, value)

    # Return a dict-like object that sets env vars when assigned
    class EnvVarSetter(dict):
        def __setitem__(self, key, value):
            set_env(key, value)
            super().__setitem__(key, value)

    return EnvVarSetter()


# ============================================================================
# Pytest hooks
# ============================================================================


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    """Skip test trees with explicit temporary root-CI discovery exclusions."""
    try:
        relative_path = collection_path.relative_to(Path(__file__).parent)
    except ValueError:
        return False

    return any(
        relative_path == excluded_path or excluded_path in relative_path.parents
        for excluded_path in TEST_DISCOVERY_EXCLUSIONS
    )


def pytest_load_initial_conftests(early_config, parser, args):
    """
    Called before any conftest files are loaded.

    This is the earliest hook that runs, making it ideal for setting
    environment variables that are needed by module-level code in conftest files.
    """
    # Set default test environment variables BEFORE any imports happen
    # This is necessary because some modules create singleton configs at import time
    if "MODE" not in os.environ:
        os.environ["MODE"] = "development"


def pytest_configure(config):
    """
    Configure pytest with custom settings.

    This runs once at the start of the test session.
    """
    config.option.importmode = "importlib"


def pytest_collection_modifyitems(config, items):
    """
    Modify test items during collection.

    Auto-marks tests based on their location:
    - Tests in /integration/ directories get the 'integration' marker
    - Tests without category markers get the 'unit' marker
    """
    # Category markers that determine test type
    category_markers = {
        "unit",
        "e2e",
        "smoke_gpu_tasks",
        "smoke_customizer_tasks",
        "smoke_customizer_automodel",
        "smoke_customizer_rl",
        "integration",
        "regression",
        "canary",
        "slow",
        "skip_in_ci",
    }

    for item in items:
        # Get current marker names
        marker_names = {marker.name for marker in item.iter_markers()}
        fspath_str = str(item.fspath)

        # Auto-mark tests in e2e directories
        if "/e2e/" in fspath_str:
            if "e2e" not in marker_names:
                item.add_marker(pytest.mark.e2e)
                marker_names.add("e2e")

        # Auto-mark integration tests (e.g., /services/evaluator/tests/integration/)
        elif "/integration/" in fspath_str:
            if "integration" not in marker_names:
                item.add_marker(pytest.mark.integration)
                marker_names.add("integration")

        # Auto-mark async tests that might be slow
        if "async" in item.name and item.get_closest_marker("timeout") is None:
            # Give async tests a longer timeout by default
            item.add_marker(pytest.mark.timeout(600))

        # Auto-mark tests without category markers as unit tests
        if not marker_names.intersection(category_markers):
            item.add_marker(pytest.mark.unit)


# ============================================================================
# Pytest command-line options
# ============================================================================


def pytest_addoption(parser):
    """
    Add custom command-line options for pytest.
    """
    parser.addoption(
        "--run-slow",
        action="store_true",
        default=False,
        help="Run slow tests (skipped by default)",
    )
    parser.addoption(
        "--run-e2e",
        action="store_true",
        default=False,
        help="Run end-to-end tests (skipped by default in quick test runs)",
    )
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=True,
        help="Run integration tests (enabled by default)",
    )


def pytest_runtest_setup(item):
    """
    Run before each test to check if it should be skipped based on command-line options.
    """
    if "slow" in [marker.name for marker in item.iter_markers()]:
        if not item.config.getoption("--run-slow"):
            skip_test("Skipping slow test (use --run-slow to run)")
    if "e2e" in [marker.name for marker in item.iter_markers()]:
        if not item.config.getoption("--run-e2e"):
            skip_test("Skipping e2e test (use --run-e2e to run)")


from xdist.scheduler.loadscope import LoadScopeScheduling  # noqa: E402

# Temporary workaround for https://github.com/pytest-dev/pytest-xdist/issues/1189
# Remove once pytest-xdist > 3.8.0 is released with the fix from PR #1299

_original_reschedule = LoadScopeScheduling._reschedule


def _patched_reschedule(self, node):
    if node not in self.registered_collections:
        return
    _original_reschedule(self, node)


LoadScopeScheduling._reschedule = _patched_reschedule  # type: ignore[invalid-assignment]
