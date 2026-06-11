# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pkgutil import resolve_name
from typing import Any, Callable, Sequence

import click
from click import Command
from typer import Typer
from typer.main import get_command as typer_get_command

from nemo_platform.cli.core.help_formatter import NmpGroup
from nemo_platform.cli.manifest import TopLevelEntry


def attach_lazy_entries(
    callback: Callable[..., Any],
    entries: Sequence[TopLevelEntry],
) -> None:
    """Attach metadata-only child entries to a group callback.

    The root callback carries the top-level manifest so `ManifestBackedNmpGroup`
    can render root help without materializing every child command first.
    """
    callback.__nmp_lazy_entries__ = tuple(entries)


class ManifestBackedNmpGroup(NmpGroup):
    """Group that renders lazy child metadata and loads real children on demand."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._lazy_entries: dict[str, TopLevelEntry] = {}
        # The callback is the stable place where the root app keeps its lazy
        # child manifest. Group help reads this metadata, and subcommand lookup
        # loads just the requested child command.
        callback = getattr(self, "callback", None)
        lazy_entries = getattr(callback, "__nmp_lazy_entries__", ())
        for entry in lazy_entries:
            self._lazy_entries[entry.name] = entry

    def list_commands(self, ctx: click.Context) -> list[str]:
        names = list(self.commands)
        for name in self._lazy_entries:
            if name not in self.commands:
                names.append(name)
        return names

    def get_command(self, ctx: click.Context, cmd_name: str) -> Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        entry = self._lazy_entries.get(cmd_name)
        if entry is None:
            return None

        loader = build_lazy_loader(entry)
        command = self._patch_command(loader())
        command.name = cmd_name
        command.hidden = command.hidden or entry.hidden
        panel = getattr(command, "rich_help_panel", None)
        if panel is None or type(panel).__name__ == "DefaultPlaceholder":
            command.rich_help_panel = entry.panel
        self.commands[cmd_name] = command
        return command


def build_lazy_loader(entry: TopLevelEntry) -> Callable[[], click.Command]:
    if entry.source == "plugin":
        return lazy_plugin_loader(entry.name, entry.import_path)
    if entry.kind == "group":
        return lazy_group_loader(entry.import_path)
    return lazy_command_loader(entry.import_path)


def lazy_plugin_loader(plugin_name: str, import_path: str) -> Callable[[], click.Command]:
    """Resolve a plugin CLI from its entry-point import path when needed."""

    def _plugin_placeholder_command(help_text: str) -> click.Command:
        return click.Group(name=plugin_name, help=help_text)

    def _load_plugin_cli() -> click.Command:
        from nemo_platform.cli.app import (
            _add_plugin_function_commands,
            _add_plugin_job_commands,
            _discover_plugin_function_entry_points,
            _discover_plugin_job_entry_points,
        )

        try:
            from nemo_platform_plugin.customization_contributor import CustomizationContributorDiscoveryError

            cli_cls = resolve_name(import_path)
            cli_obj = cli_cls()
            plugin_app = cli_obj.get_cli()
        except CustomizationContributorDiscoveryError as exc:
            raise click.ClickException(str(exc)) from exc
        except Exception:
            return _plugin_placeholder_command(f"Plugin commands for {plugin_name} are unavailable.")

        job_entry_points = _discover_plugin_job_entry_points()
        if job_entry_points is not None:
            plugin_jobs = {}
            for job_name, job_entry_point in job_entry_points.items():
                if not job_name.startswith(f"{plugin_name}."):
                    continue
                try:
                    plugin_jobs[job_name] = job_entry_point.load()
                except Exception:
                    continue
            if plugin_jobs:
                _add_plugin_job_commands(plugin_app, plugin_jobs, cli=cli_obj)

        # Functions live alongside jobs at the plugin level; mirror the
        # same per-plugin filtering so a multi-plugin install only sees
        # this plugin's functions in the resolved CLI tree.
        function_entry_points = _discover_plugin_function_entry_points()
        if function_entry_points is not None:
            plugin_functions = {}
            for fn_name, fn_entry_point in function_entry_points.items():
                if not fn_name.startswith(f"{plugin_name}."):
                    continue
                try:
                    plugin_functions[fn_name] = fn_entry_point.load()
                except Exception:
                    continue
            if plugin_functions:
                _add_plugin_function_commands(plugin_app, plugin_functions, cli=cli_obj)

        try:
            return typer_get_command(plugin_app)
        except RuntimeError:
            return _plugin_placeholder_command(plugin_app.info.help or f"Plugin commands for {plugin_name}.")

    return _load_plugin_cli


def lazy_group_loader(import_path: str) -> Callable[[], click.Command]:
    """Resolve a Typer app from ``module:attribute`` when needed."""

    def _load_group() -> click.Command:
        nested_name = "__lazy_group__"
        temp_app = Typer()
        temp_app.add_typer(resolve_name(import_path), name=nested_name)
        root_command = typer_get_command(temp_app)
        nested_command = root_command.get_command(click.Context(root_command), nested_name)
        if nested_command is None:
            raise click.ClickException(f"Failed to build nested CLI group for {import_path!r}")
        return nested_command

    def _lazy_loader() -> click.Command:
        try:
            return _load_group()
        except (ModuleNotFoundError, AttributeError) as exc:
            raise click.ClickException(f"Failed to load CLI group {import_path!r}: {exc}") from exc

    return _lazy_loader


def lazy_command_loader(import_path: str) -> Callable[[], click.Command]:
    """Resolve a top-level command from ``module:attribute`` when needed."""

    def _load_command() -> click.Command:
        holder_name = "__lazy_command_holder__"
        command = resolve_name(import_path)
        holder_app = Typer()
        holder_app.command()(command)
        temp_app = Typer()
        temp_app.add_typer(holder_app, name=holder_name)
        root_command = typer_get_command(temp_app)
        holder_command = root_command.get_command(click.Context(root_command), holder_name)
        if holder_command is None or not isinstance(holder_command, click.Group):
            raise click.ClickException(f"Failed to build nested CLI command holder for {import_path!r}")
        nested_commands = list(holder_command.commands.values())
        if len(nested_commands) != 1:
            raise click.ClickException(f"Failed to build nested CLI command for {import_path!r}")
        nested_command = nested_commands[0]
        if nested_command is None:
            raise click.ClickException(f"Failed to build nested CLI command for {import_path!r}")
        return nested_command

    def _lazy_loader() -> click.Command:
        try:
            return _load_command()
        except (ModuleNotFoundError, AttributeError) as exc:
            raise click.ClickException(f"Failed to load CLI command {import_path!r}: {exc}") from exc

    return _lazy_loader
