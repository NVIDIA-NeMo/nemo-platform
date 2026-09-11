# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Base-URL resolution against the shared CLI context.

The bug these cover: `nemo insights` defaulted to localhost while the rest of
the CLI followed the configured context, so every command failed against a
remote deployment that `nemo workspaces list` reached fine.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from nemo_insights_plugin.cli_context import (
    DEFAULT_WORKSPACE,
    active_context_base_url,
    base_url_from_context,
    resolve_workspace,
)
from nemo_insights_plugin.contracts.profile import DEFAULT_BASE_URL


@contextmanager
def cli_state(obj: object) -> Iterator[None]:
    """Push a Click context carrying *obj*, the way the `nemo` root callback does."""
    with click.Context(click.Command("insights"), obj=obj):
        yield


def test_base_url_from_context_is_none_outside_a_cli_invocation() -> None:
    assert base_url_from_context() is None


def test_ambient_context_wins_over_the_config_file(
    use_nmp_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Global `nemo --base-url` / `--context` reach us only through the context object.

    They are recorded as overrides there and are invisible to a fresh config
    read, so preferring the file would silently drop them.
    """
    use_nmp_config(base_url="https://from-file.example")

    with cli_state(
        SimpleNamespace(
            get_sdk_context=lambda: SimpleNamespace(cluster=SimpleNamespace(base_url="https://from-flag.example/"))
        )
    ):
        # Trailing slash stripped: pydantic adds one, the user did not.
        assert active_context_base_url() == "https://from-flag.example"


def test_falls_back_to_the_config_file_without_a_usable_context(
    use_nmp_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    use_nmp_config(base_url="https://from-file.example")

    assert active_context_base_url() == "https://from-file.example"
    with cli_state(SimpleNamespace()):  # a context object with no get_sdk_context
        assert active_context_base_url() == "https://from-file.example"


def test_a_raising_context_object_does_not_fail_the_command(
    use_nmp_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode() -> object:
        raise RuntimeError("unreadable context")

    use_nmp_config(base_url="https://from-file.example")

    with cli_state(SimpleNamespace(get_sdk_context=explode)):
        assert active_context_base_url() == "https://from-file.example"


def test_localhost_is_the_last_resort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_CONFIG_FILE", str(tmp_path / "missing.yaml"))

    assert active_context_base_url() == DEFAULT_BASE_URL


def test_a_deliberate_cli_abort_is_not_swallowed(
    use_nmp_config: Callable[..., Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--context nope` must fail here exactly as it does for `nemo workspaces list`.

    Falling back to the config file would run the command against the default
    context — a different platform than the one the user named.
    """

    def abort() -> object:
        raise click.exceptions.Exit(1)

    use_nmp_config(base_url="https://from-file.example")

    with cli_state(SimpleNamespace(get_sdk_context=abort)), pytest.raises(click.exceptions.Exit):
        active_context_base_url()


def test_workspace_comes_from_the_context_not_a_hardcoded_default(
    use_nmp_config: Callable[..., Path],
) -> None:
    """`--workspace` unset means the context's workspace, not the string "default".

    Defaulting to "default" quietly queried the wrong workspace for anyone
    whose context names another one.
    """
    use_nmp_config(workspace="team-space")

    assert resolve_workspace(None) == "team-space"
    assert resolve_workspace("explicit-space") == "explicit-space"


def test_workspace_falls_back_to_default_without_a_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NMP_CONFIG_FILE", str(tmp_path / "missing.yaml"))

    assert resolve_workspace(None) == DEFAULT_WORKSPACE


def test_ambient_workspace_wins_over_the_config_file(use_nmp_config: Callable[..., Path]) -> None:
    use_nmp_config(workspace="from-file")

    with cli_state(SimpleNamespace(get_sdk_context=lambda: SimpleNamespace(workspace="from-flag"))):
        assert resolve_workspace(None) == "from-flag"
