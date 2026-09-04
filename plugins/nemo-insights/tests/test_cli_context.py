# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base-URL resolution against the shared CLI context.

The bug these cover: `nemo insights` defaulted to localhost while the rest of
the CLI followed the configured context, so every command failed against a
remote deployment that `nemo workspaces list` reached fine.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from nemo_insights_plugin.cli_context import active_context_base_url, base_url_from_context
from nemo_insights_plugin.contracts.profile import DEFAULT_BASE_URL


@contextmanager
def cli_state(obj: object) -> Iterator[None]:
    """Push a Click context carrying *obj*, the way the `nemo` root callback does."""
    with click.Context(click.Command("insights"), obj=obj):
        yield


def write_config(path: Path, base_url: str) -> Path:
    path.write_text(
        "current_context: prod\n"
        "contexts:\n"
        "  - name: prod\n    cluster: prod-cluster\n    user: prod-user\n"
        "clusters:\n"
        f"  - name: prod-cluster\n    base_url: {base_url}\n"
        "users:\n"
        "  - name: prod-user\n    type: oauth\n    token: t\n",
        encoding="utf-8",
    )
    return path


def test_base_url_from_context_is_none_outside_a_cli_invocation() -> None:
    assert base_url_from_context() is None


def test_ambient_context_wins_over_the_config_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Global `nemo --base-url` / `--context` reach us only through the context object.

    They are recorded as overrides there and are invisible to a fresh config
    read, so preferring the file would silently drop them.
    """
    monkeypatch.setenv("NMP_CONFIG_FILE", str(write_config(tmp_path / "config.yaml", "https://from-file.example")))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)

    with cli_state(
        SimpleNamespace(
            get_sdk_context=lambda: SimpleNamespace(cluster=SimpleNamespace(base_url="https://from-flag.example/"))
        )
    ):
        # Trailing slash stripped: pydantic adds one, the user did not.
        assert active_context_base_url() == "https://from-flag.example"


def test_falls_back_to_the_config_file_without_a_usable_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NMP_CONFIG_FILE", str(write_config(tmp_path / "config.yaml", "https://from-file.example")))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)

    assert active_context_base_url() == "https://from-file.example"
    with cli_state(SimpleNamespace()):  # a context object with no get_sdk_context
        assert active_context_base_url() == "https://from-file.example"


def test_a_raising_context_object_does_not_fail_the_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> object:
        raise RuntimeError("unreadable context")

    monkeypatch.setenv("NMP_CONFIG_FILE", str(write_config(tmp_path / "config.yaml", "https://from-file.example")))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)

    with cli_state(SimpleNamespace(get_sdk_context=explode)):
        assert active_context_base_url() == "https://from-file.example"


def test_localhost_is_the_last_resort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_CONFIG_FILE", str(tmp_path / "missing.yaml"))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)

    assert active_context_base_url() == DEFAULT_BASE_URL


def test_a_deliberate_cli_abort_is_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--context nope` must fail here exactly as it does for `nemo workspaces list`.

    Falling back to the config file would run the command against the default
    context — a different platform than the one the user named.
    """

    def abort() -> object:
        raise click.exceptions.Exit(1)

    monkeypatch.setenv("NMP_CONFIG_FILE", str(write_config(tmp_path / "config.yaml", "https://from-file.example")))
    monkeypatch.delenv("NMP_BASE_URL", raising=False)

    with cli_state(SimpleNamespace(get_sdk_context=abort)), pytest.raises(click.exceptions.Exit):
        active_context_base_url()
