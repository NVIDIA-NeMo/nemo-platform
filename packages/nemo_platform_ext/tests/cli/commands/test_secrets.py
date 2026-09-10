# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Wire-level tests for ``nemo secrets`` against a scripted typed client.

Each test drives the real Typer command with a ``NemoClient`` whose transport
records the HTTP requests, so the assertions pin the exact method, path, query
string, and JSON body the command sends.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest
from nemo_platform_ext.cli.app import app
from nemo_platform_ext.cli.core.context import CLIContext
from nemo_platform_plugin.client.client import NemoClient
from typer.testing import CliRunner

SECRET = {
    "name": "hf-token",
    "workspace": "default",
    "description": "HF token",
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


@dataclass
class Recorder:
    """Records requests and answers each with the next scripted response."""

    responses: list[httpx.Response]
    requests: list[httpx.Request] = field(default_factory=list)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self.responses:
            raise AssertionError(f"unexpected request {request.method} {request.url}")
        return self.responses.pop(0)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


def make_runner(recorder: Recorder, *, workspace: str | None = "default") -> tuple[CliRunner, CLIContext]:
    client = NemoClient(
        base_url="http://test",
        workspace=workspace,
        http_client=httpx.Client(transport=httpx.MockTransport(recorder)),
    )
    state = CLIContext(overrides={"base_url": "http://test", "output_format": "json"}, _client=client)
    return CliRunner(), state


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    config_file = tmp_path / "config.yaml"
    config_file.touch()
    monkeypatch.setenv("NMP_CONFIG_FILE", str(config_file))
    monkeypatch.delenv("NMP_ACCESS_TOKEN", raising=False)


def test_get_uses_client_default_workspace() -> None:
    recorder = Recorder([httpx.Response(200, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "get", "hf-token"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.method == "GET"
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets/hf-token"
    assert json.loads(result.stdout)["name"] == "hf-token"


def test_get_explicit_workspace_overrides_default() -> None:
    recorder = Recorder([httpx.Response(200, json={**SECRET, "workspace": "other"})])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "get", "hf-token", "--workspace", "other"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/other/secrets/hf-token"


def test_get_without_any_workspace_is_usage_error() -> None:
    recorder = Recorder([])
    runner, state = make_runner(recorder, workspace=None)

    result = runner.invoke(app, ["secrets", "get", "hf-token"], obj=state)

    assert result.exit_code == 2
    assert "Missing workspace" in result.stderr
    assert recorder.requests == []


def test_access_returns_value() -> None:
    recorder = Recorder([httpx.Response(200, json={"name": "hf-token", "workspace": "default", "value": "s3cret"})])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "access", "hf-token"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets/hf-token/access"
    assert json.loads(result.stdout)["value"] == "s3cret"


def test_create_sends_plaintext_body_once() -> None:
    recorder = Recorder([httpx.Response(201, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(
        app, ["secrets", "create", "hf-token", "--value", "s3cret", "--description", "HF token"], obj=state
    )

    assert result.exit_code == 0, result.output
    assert len(recorder.requests) == 1
    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets"
    assert json.loads(recorder.last.content) == {"name": "hf-token", "description": "HF token", "value": "s3cret"}


def test_create_without_description_omits_it_from_body() -> None:
    recorder = Recorder([httpx.Response(201, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "create", "hf-token", "--value", "s3cret"], obj=state)

    assert result.exit_code == 0, result.output
    assert json.loads(recorder.last.content) == {"name": "hf-token", "value": "s3cret"}


def test_create_reads_value_from_stdin() -> None:
    recorder = Recorder([httpx.Response(201, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "create", "hf-token", "--from-file", "-"], obj=state, input="piped\n")

    assert result.exit_code == 0, result.output
    assert json.loads(recorder.last.content)["value"] == "piped"


def test_create_requires_name() -> None:
    recorder = Recorder([])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "create", "--value", "v"], obj=state)

    assert result.exit_code == 2
    assert "name" in result.stderr
    assert recorder.requests == []


def test_update_only_sends_provided_fields() -> None:
    recorder = Recorder([httpx.Response(200, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "update", "hf-token", "--description", "new"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.method == "PATCH"
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets/hf-token"
    assert json.loads(recorder.last.content) == {"description": "new"}


def test_update_value_is_sent_in_plaintext() -> None:
    recorder = Recorder([httpx.Response(200, json=SECRET)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "update", "hf-token", "--value", "n3w"], obj=state)

    assert result.exit_code == 0, result.output
    assert json.loads(recorder.last.content) == {"value": "n3w"}


def test_delete() -> None:
    recorder = Recorder([httpx.Response(204)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "delete", "hf-token"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.method == "DELETE"
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets/hf-token"
    assert "Deleted successfully" in result.stdout


def _page(items: list[dict], page: int, total_pages: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "data": items,
            "pagination": {
                "page": page,
                "page_size": 1,
                "current_page_size": len(items),
                "total_pages": total_pages,
                "total_results": total_pages,
            },
        },
    )


def test_list_passes_pagination_query_params_and_warns() -> None:
    recorder = Recorder([_page([SECRET], 1, 2)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "list", "--page", "1", "--page-size", "1"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.url.path == "/apis/secrets/v2/workspaces/default/secrets"
    assert dict(recorder.last.url.params) == {"page": "1", "page_size": "1"}
    body = json.loads(result.stdout)
    assert [item["name"] for item in body["data"]] == ["hf-token"]
    assert body["pagination"]["total_pages"] == 2
    assert "More pages" in result.stderr


def test_list_all_pages_follows_every_page() -> None:
    recorder = Recorder([_page([SECRET], 1, 2), _page([{**SECRET, "name": "second"}], 2, 2)])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "list", "--page-size", "1", "--all-pages"], obj=state)

    assert result.exit_code == 0, result.output
    assert [dict(r.url.params).get("page") for r in recorder.requests] == [None, "2"]
    body = json.loads(result.stdout)
    assert [item["name"] for item in body["data"]] == ["hf-token", "second"]
    assert body["pagination"]["total_results"] == 2
    assert "More pages" not in result.stderr


def test_list_table_output_uses_default_columns() -> None:
    recorder = Recorder([_page([SECRET], 1, 1)])
    runner, state = make_runner(recorder)
    state.overrides["output_format"] = "table"

    result = runner.invoke(app, ["secrets", "list", "-f", "table"], obj=state)

    assert result.exit_code == 0, result.output
    output = result.stdout.lower()
    assert "name" in output and "workspace" in output and "created_at" in output
    assert "description" not in output


def test_admin_rotate_encryption_keys() -> None:
    recorder = Recorder([httpx.Response(200, json={"rotated_secrets": 3, "success": True})])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "admin", "rotate-encryption-keys"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.last.method == "POST"
    assert recorder.last.url.path == "/apis/secrets/v2/rotate-encryption-keys"
    assert json.loads(result.stdout) == {"rotated_secrets": 3, "success": True}


def test_http_error_maps_to_remote_error_exit_code() -> None:
    recorder = Recorder([httpx.Response(404, json={"detail": "Secret 'nope' not found"})])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "get", "nope"], obj=state)

    assert result.exit_code == 3
    assert "Not found: (404) Secret 'nope' not found" in result.stderr
    assert "nemo secrets list" in result.stderr


def test_code_output_does_not_send_request_and_masks_secret() -> None:
    recorder = Recorder([])
    runner, state = make_runner(recorder)

    result = runner.invoke(app, ["secrets", "create", "hf-token", "--value", "topsecret", "-f", "code"], obj=state)

    assert result.exit_code == 0, result.output
    assert recorder.requests == []
    assert "from nemo_platform_plugin.secrets.client import SecretsClient" in result.stdout
    assert 'client = SecretsClient(base_url="http://test/")' in result.stdout
    assert "topsecret" not in result.stdout
    assert "NeMoPlatform" not in result.stdout
