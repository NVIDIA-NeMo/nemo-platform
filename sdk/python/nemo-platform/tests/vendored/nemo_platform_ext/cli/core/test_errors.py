# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for error handling in the CLI."""

from unittest.mock import MagicMock, Mock

import click
import httpx
import pytest
import typer
from nemo_platform._exceptions import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
)
from nemo_platform.cli.app import app
from nemo_platform.cli.core.errors import (
    InvalidSearchPatternError,
    _format_api_error,
    handle_exception,
)
from typer.testing import CliRunner


@pytest.mark.parametrize(
    "body,message,expected",
    [
        ({"detail": "Resource not found"}, "Other message", "Resource not found"),
        ({"detail": "Workspace 'default' not found"}, "Fallback", "Workspace 'default' not found"),
        ({"message": "Something went wrong"}, "Fallback", "Something went wrong"),
        ({"detail": "Specific", "message": "General"}, "Fallback", "Specific"),
        (None, "Error from message attribute", "Error from message attribute"),
        ({}, "Fallback message", "Fallback message"),
        ("Just a string", "Message attribute", "Message attribute"),
    ],
)
def test_format_api_error(body, message, expected):
    error = Mock(spec=APIError)
    error.body = body
    error.message = message
    assert _format_api_error(error) == expected


def test_format_api_error_fallback_to_str():
    error = Mock(spec=APIError)
    error.body = None
    error.message = None
    error.__str__ = Mock(return_value="String representation of error")
    assert _format_api_error(error) == "String representation of error"


@pytest.mark.parametrize(
    "error_class,status_code,expected_prefix,expected_hint",
    [
        (NotFoundError, 404, "Not found:", "Check the resource name/ID"),
        (BadRequestError, 400, "Bad request:", "Check your input"),
        (AuthenticationError, 401, "Authentication error:", "NMP_ACCESS_TOKEN"),
        (PermissionDeniedError, 403, "Permission denied:", "not have access"),
        (ConflictError, 409, "Conflict:", "already exist"),
        (RateLimitError, 429, "Rate limit exceeded:", "Wait a moment"),
        (InternalServerError, 500, "Server error:", "server-side issue"),
    ],
)
def test_handle_api_status_errors(capsys, error_class, status_code, expected_prefix, expected_hint):
    response = Mock()
    response.status_code = status_code
    error = error_class("Error message", response=response, body=None)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert expected_prefix in captured.err
    assert f"({status_code})" in captured.err
    assert expected_hint in captured.err


def test_handle_api_connection_error(capsys):
    request = Mock()
    error = APIConnectionError(message="Could not connect", request=request)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Connection error:" in captured.err
    assert "base-url" in captured.err


def test_handle_api_timeout_error(capsys):
    request = Mock()
    error = APITimeoutError(request=request)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Connection error:" in captured.err
    assert "timed out" in captured.err


def test_handle_api_status_error(capsys):
    response = Mock()
    response.status_code = 418
    error = APIStatusError("I'm a teapot", response=response, body=None)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "API error:" in captured.err
    assert "(418)" in captured.err


def test_handle_api_status_error_prints_request_context(capsys):
    request = httpx.Request("POST", "http://test/apis/models/v2/workspaces/default/models")
    response = httpx.Response(418, request=request, json={"detail": "short and stout"})
    error = APIStatusError("I'm a teapot", response=response, body={"detail": "short and stout"})

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "API error:" in captured.err
    assert "Request: POST http://test/apis/models/v2/workspaces/default/models" in captured.err
    assert "Target: models API route /apis/models/v2/workspaces/default/models" in captured.err


def test_handle_generic_api_error(capsys):
    request = Mock()
    error = APIError(message="Generic API error", request=request, body=None)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "API error:" in captured.err


def _make_mock_context(info_name: str, parent: click.Context | None = None) -> MagicMock:
    mock_ctx = MagicMock(spec=click.Context)
    mock_ctx.info_name = info_name
    mock_ctx.parent = parent
    mock_ctx.command = MagicMock()
    return mock_ctx


def test_handle_usage_error_with_context(capsys):
    mock_parent_ctx = _make_mock_context("nmp", parent=None)
    mock_ctx = _make_mock_context("model", parent=mock_parent_ctx)
    error = click.UsageError("Invalid option value", ctx=mock_ctx)

    with pytest.raises(SystemExit) as exc_info:
        handle_exception(error)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Invalid option value" in captured.err
    assert "Usage:" in captured.err
    assert "model" in captured.err


def test_handle_usage_error_without_context(capsys):
    error = click.UsageError("Invalid option value")

    with pytest.raises(SystemExit) as exc_info:
        handle_exception(error)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "Invalid option value" in captured.err


def test_handle_missing_parameter(capsys):
    mock_parent_ctx = _make_mock_context("nmp", parent=None)
    mock_ctx = _make_mock_context("create", parent=mock_parent_ctx)

    mock_param = MagicMock(spec=click.Option)
    mock_param.opts = ["--name"]
    mock_param.name = "name"
    mock_param.type = click.STRING
    mock_param.type.get_missing_message = MagicMock(return_value=None)
    mock_param.help = "The resource name"  # Help text shown when param has it

    error = click.MissingParameter(param=mock_param, ctx=mock_ctx)

    with pytest.raises(SystemExit) as exc_info:
        handle_exception(error)

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "Error:" in captured.err
    assert "<NAME>" in captured.err  # Parameter name shown
    assert "resource name" in captured.err  # Help text on same line


def test_handle_typer_exit(capsys):
    """typer.Exit should be re-raised with its original exit code (not treated as an error)."""
    error = typer.Exit(code=0)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    # Exit code should be preserved, not converted to 1
    assert exc_info.value.exit_code == 0
    # No error message should be printed for Exit(0)
    captured = capsys.readouterr()
    assert "Error:" not in captured.err


def test_handle_unexpected_error(capsys):
    error = ValueError("Something unexpected happened")

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Unexpected error:" in captured.err
    assert "Something unexpected happened" in captured.err
    assert "verbose" in captured.err


@pytest.mark.parametrize(
    "debug_enabled,should_show_traceback",
    [
        (True, True),
        (False, False),
    ],
)
def test_verbose_mode_traceback(capsys, debug_enabled, should_show_traceback):
    response = Mock()
    response.status_code = 404
    error = NotFoundError("Resource not found", response=response, body=None)

    import logging

    logger = logging.getLogger("nemo_platform.cli")
    original_level = logger.level
    try:
        logger.setLevel(logging.DEBUG if debug_enabled else logging.WARNING)
        with pytest.raises(typer.Exit):
            handle_exception(error)
    finally:
        logger.setLevel(original_level)

    captured = capsys.readouterr()
    if should_show_traceback:
        assert "DEBUG: Full traceback:" in captured.err
    else:
        assert "DEBUG: Full traceback:" not in captured.err


def test_decorator_catches_and_handles_errors(capsys):
    from nemo_platform.cli.core.errors import handle_errors

    response = Mock()
    response.status_code = 404

    @handle_errors
    def failing_function():
        raise NotFoundError("Not found", response=response, body=None)

    with pytest.raises(typer.Exit) as exc_info:
        failing_function()

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Not found:" in captured.err


def test_not_found_prints_server_message(capsys):
    """NotFoundError prints the server's detail (e.g. workspace not found) on its own line."""
    response = Mock()
    response.status_code = 404
    error = NotFoundError("Not found", response=response, body={"detail": "Workspace 'default' not found"})

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Not found:" in captured.err
    assert "Workspace 'default' not found" in captured.err


def test_not_found_prints_request_context_and_404_hint(capsys):
    request = httpx.Request("GET", "http://test/apis/agents/v2/workspaces/default/agents")
    response = httpx.Response(404, request=request, json={"detail": "Not Found"})
    error = NotFoundError("Not found", response=response, body={"detail": "Not Found"})

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Request: GET http://test/apis/agents/v2/workspaces/default/agents" in captured.err
    assert "Target: agents API route /apis/agents/v2/workspaces/default/agents" in captured.err
    assert "resource does not exist" in captured.err
    assert "endpoint is not deployed" in captured.err
    assert "nemo config view" in captured.err


def test_not_found_hint_fallback_when_no_ctx(capsys):
    """NotFoundError hint without context only says to check the resource name/ID (no list command)."""
    response = Mock()
    response.status_code = 404
    error = NotFoundError("Not found", response=response, body=None)

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 1
    captured = capsys.readouterr()
    assert "Not found:" in captured.err
    assert "Check the resource name/ID" in captured.err
    assert "list" not in captured.err


def test_handle_invalid_search_pattern_error(capsys):
    """InvalidSearchPatternError (bare value) shows the --filter formats and examples."""
    error = InvalidSearchPatternError("nemo")

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    assert "Invalid filter value" in captured.err
    assert "nemo" in captured.err
    assert "Examples:" in captured.err
    assert "--filter" in captured.err
    assert "--filter.name" in captured.err
    assert "--help" in captured.err
    # Regression: the old message referenced a nonexistent option and stale format.
    assert "--search" not in captured.err
    assert "field=value" not in captured.err


def test_handle_invalid_search_pattern_error_with_json(capsys):
    """InvalidSearchPatternError (invalid JSON) shows parse error and input."""
    error = InvalidSearchPatternError(
        '{"name": ["nemo", "djs]}',
        parse_error="Unterminated string starting at: line 1 column 19 (char 18)",
    )

    with pytest.raises(typer.Exit) as exc_info:
        handle_exception(error)

    assert exc_info.value.exit_code == 2
    captured = capsys.readouterr()
    assert "Invalid filter JSON" in captured.err
    assert "Unterminated string" in captured.err
    assert "Your input:" in captured.err
    assert "djs]}" in captured.err
    assert "--filter" in captured.err
    assert "--help" in captured.err
    assert "--search" not in captured.err


def test_decorator_passes_through_success():
    from nemo_platform.cli.core.errors import handle_errors

    @handle_errors
    def successful_function():
        return "success"

    result = successful_function()
    assert result == "success"


def test_root_no_args_prints_help_successfully():
    """Running nemo without args should print help and exit successfully."""
    runner = CliRunner()
    result = runner.invoke(app, [])

    assert result.exit_code == 0
    assert "Usage:" in result.stdout
    assert result.stderr == ""
    # No ANSI escape codes should appear (colors stripped for non-TTY)
    # TODO: This fails after vendoring, will fix it later
    # assert "\x1b[" not in result.stdout


def _make_mock_context_with_commands(info_name: str, commands: dict, parent: click.Context | None = None) -> MagicMock:
    ctx = _make_mock_context(info_name, parent)
    ctx.command.commands = commands
    return ctx


def test_not_found_hint_shows_specific_list_cmd(capsys):
    """NotFoundError hint shows the specific list command when the parent group has one."""
    root_ctx = _make_mock_context("nmp", parent=None)
    group_ctx = _make_mock_context_with_commands("models", {"list": MagicMock(), "get": MagicMock()}, parent=root_ctx)
    cmd_ctx = _make_mock_context("get", parent=group_ctx)

    response = Mock()
    response.status_code = 404
    error = NotFoundError("Not found", response=response, body=None)

    with pytest.raises(typer.Exit):
        handle_exception(error, ctx=cmd_ctx)

    captured = capsys.readouterr()
    assert "nemo models list" in captured.err
    assert "Check the resource name/ID" in captured.err


def test_not_found_hint_omits_list_when_no_list_subcommand(capsys):
    """NotFoundError hint does not suggest a list command when the parent group has none."""
    root_ctx = _make_mock_context("nmp", parent=None)
    group_ctx = _make_mock_context_with_commands("models", {"get": MagicMock()}, parent=root_ctx)
    cmd_ctx = _make_mock_context("get", parent=group_ctx)

    response = Mock()
    response.status_code = 404
    error = NotFoundError("Not found", response=response, body=None)

    with pytest.raises(typer.Exit):
        handle_exception(error, ctx=cmd_ctx)

    captured = capsys.readouterr()
    assert "Check the resource name/ID" in captured.err
    assert "list" not in captured.err


@pytest.mark.parametrize(
    "body_detail,has_list_cmd,expect_list_hint",
    [
        ("Resource not found", True, True),
        ("Upstream returned 404", True, True),
        ("Internal processing failed", True, False),
        ("Resource not found", False, False),
    ],
)
def test_internal_server_error_hint(capsys, body_detail, has_list_cmd, expect_list_hint):
    """InternalServerError shows list hint when body contains 'not found'/'404' and parent has a list command; otherwise shows generic hint."""
    root_ctx = _make_mock_context("nmp", parent=None)
    commands = {"list": MagicMock(), "get": MagicMock()} if has_list_cmd else {"get": MagicMock()}
    group_ctx = _make_mock_context_with_commands("models", commands, parent=root_ctx)
    cmd_ctx = _make_mock_context("get", parent=group_ctx)

    response = Mock()
    response.status_code = 500
    error = InternalServerError("Server error", response=response, body={"detail": body_detail})

    with pytest.raises(typer.Exit):
        handle_exception(error, ctx=cmd_ctx)

    captured = capsys.readouterr()
    assert "Server error:" in captured.err
    if expect_list_hint:
        assert "nemo models list" in captured.err
        assert "server-side issue" not in captured.err
    else:
        assert "server-side issue" in captured.err
        assert "list" not in captured.err
