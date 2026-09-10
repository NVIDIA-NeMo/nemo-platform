# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for ``nemo secrets`` against the in-process Secrets service."""

import json
import uuid

from nemo_platform_ext.cli.app import app

from ..utils import assert_exit_code


def _name() -> str:
    return f"secret-{uuid.uuid4().hex[:8]}"


def test_secrets_lifecycle(runner, random_workspace: str) -> None:
    name = _name()

    result = runner.invoke(
        app,
        ["secrets", "create", name, "--value", "s3cret", "--description", "demo", "--workspace", random_workspace],
    )
    assert_exit_code(result, 0)
    created = json.loads(result.stdout)
    assert created["name"] == name
    assert created["workspace"] == random_workspace
    assert created["description"] == "demo"
    assert "value" not in created

    result = runner.invoke(app, ["secrets", "get", name, "--workspace", random_workspace])
    assert_exit_code(result, 0)
    assert json.loads(result.stdout)["name"] == name

    result = runner.invoke(app, ["secrets", "access", name, "--workspace", random_workspace])
    assert_exit_code(result, 0)
    assert json.loads(result.stdout)["value"] == "s3cret"

    result = runner.invoke(app, ["secrets", "list", "--workspace", random_workspace])
    assert_exit_code(result, 0)
    listed = json.loads(result.stdout)
    assert [item["name"] for item in listed["data"]] == [name]
    assert listed["pagination"]["total_results"] == 1

    result = runner.invoke(
        app, ["secrets", "update", name, "--value", "n3w", "--description", "changed", "--workspace", random_workspace]
    )
    assert_exit_code(result, 0)
    assert json.loads(result.stdout)["description"] == "changed"
    result = runner.invoke(app, ["secrets", "access", name, "--workspace", random_workspace])
    assert json.loads(result.stdout)["value"] == "n3w"

    result = runner.invoke(app, ["secrets", "delete", name, "--workspace", random_workspace])
    assert_exit_code(result, 0)
    assert "Deleted successfully" in result.stdout

    result = runner.invoke(app, ["secrets", "get", name, "--workspace", random_workspace])
    assert_exit_code(result, 3)
    assert "Not found" in result.stderr


def test_secrets_create_from_stdin(runner, random_workspace: str) -> None:
    name = _name()
    result = runner.invoke(
        app, ["secrets", "create", name, "--from-file", "-", "--workspace", random_workspace], input="piped\n"
    )
    assert_exit_code(result, 0)

    result = runner.invoke(app, ["secrets", "access", name, "--workspace", random_workspace])
    assert json.loads(result.stdout)["value"] == "piped"


def test_secrets_list_all_pages(runner, random_workspace: str) -> None:
    names = sorted(_name() for _ in range(3))
    for name in names:
        assert_exit_code(
            runner.invoke(app, ["secrets", "create", name, "--value", "v", "--workspace", random_workspace]), 0
        )

    result = runner.invoke(app, ["secrets", "list", "--workspace", random_workspace, "--page-size", "2"])
    assert_exit_code(result, 0)
    first_page = json.loads(result.stdout)
    assert len(first_page["data"]) == 2
    assert first_page["pagination"]["total_pages"] == 2
    assert "More pages" in result.stderr

    result = runner.invoke(app, ["secrets", "list", "--workspace", random_workspace, "--page-size", "2", "--all-pages"])
    assert_exit_code(result, 0)
    all_pages = json.loads(result.stdout)
    assert sorted(item["name"] for item in all_pages["data"]) == names
    assert all_pages["pagination"]["total_results"] == 3
    assert "More pages" not in result.stderr


def test_secrets_code_output_masks_value(runner, random_workspace: str) -> None:
    result = runner.invoke(
        app,
        ["secrets", "create", "code-secret", "--value", "topsecret", "--workspace", random_workspace, "-f", "code"],
    )
    assert_exit_code(result, 0)
    assert "from nemo_platform_plugin.secrets.client import SecretsClient" in result.stdout
    assert "client.create_secret(" in result.stdout
    assert "topsecret" not in result.stdout
    assert '"***"' in result.stdout
    assert "NeMoPlatform" not in result.stdout

    # Nothing was created: code output never sends the request.
    result = runner.invoke(app, ["secrets", "list", "--workspace", random_workspace])
    assert json.loads(result.stdout)["data"] == []


def test_secrets_missing_workspace_is_usage_error(runner) -> None:
    result = runner.invoke(
        app,
        ["secrets", "get", "x"],
        obj=None,
    )
    # The injected client has no default workspace and none was passed.
    assert result.exit_code in (2, 3)


def test_secrets_create_rejects_invalid_name_locally(runner, random_workspace: str) -> None:
    result = runner.invoke(app, ["secrets", "create", "x", "--value", "v", "--workspace", random_workspace])
    assert_exit_code(result, 2)
    assert "Invalid input" in result.stderr
    assert "name" in result.stderr
