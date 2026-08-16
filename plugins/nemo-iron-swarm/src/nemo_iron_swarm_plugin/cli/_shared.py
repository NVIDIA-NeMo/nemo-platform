# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Preamble and option parsing shared by the ``nemo iron-swarm`` command modules.

Kept in one place so "which commands gate on host readiness" and "what counts as a valid preset"
are each one decision rather than one per command module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, get_args

import typer
from nemo_iron_swarm_plugin.cli import checks
from nemo_iron_swarm_plugin.cli.client import base_url, make_sdk
from nemo_iron_swarm_plugin.config import IronSwarmConfig
from nemo_iron_swarm_plugin.entities import IronSwarmManifest
from nemo_iron_swarm_plugin.jobs.manifest import DEFENDER_ENTRIES

# The entity's own Literal is the single source of truth for the valid presets.
ATTACK_INTENSITIES: tuple[str, ...] = get_args(IronSwarmManifest.model_fields["attack_intensity"].annotation)


@dataclass(frozen=True)
class CommandContext:
    """Resolved preamble every SDK-backed command needs."""

    config: IronSwarmConfig
    sdk: Any
    base_url: str
    workspace: str


def command_context(workspace: str | None, *, preflight: bool = True) -> CommandContext:
    """Shared command preamble: config, host preflight, SDK client, resolved workspace.

    Making *preflight* an explicit argument keeps the "which commands gate on host readiness"
    policy one decision instead of one per command.
    """
    config = IronSwarmConfig.get()
    if preflight:
        checks.require_preflight(config)
    url = base_url()
    return CommandContext(
        config=config,
        sdk=make_sdk(url),
        base_url=url,
        workspace=workspace or config.default_workspace,
    )


def parse_env_pairs(pairs: list[str]) -> dict[str, str]:
    """Parse repeated ``KEY=VALUE`` flags into a dict, failing loudly on a malformed pair."""
    env: dict[str, str] = {}
    for pair in pairs:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            typer.secho(f"Error: --env expects KEY=VALUE, got {pair!r}.", fg="red")
            raise typer.Exit(code=1)
        env[key] = value
    return env


def validated_intensity(value: str | None) -> str | None:
    """Reject an unknown attacker preset, which the job would otherwise read as ``standard``.

    Validated against the entity's own Literal, not ``INTENSITY_GARAK``: that dict holds only the presets
    that emit a ``garak:`` block, so ``standard`` — a legal value meaning "leave iron-swarm's defaults" —
    is deliberately absent from it.
    """
    if value is None:
        return None
    if value not in ATTACK_INTENSITIES:
        choices = ", ".join(ATTACK_INTENSITIES)
        typer.secho(f"Error: --attack-intensity must be one of {choices}; got {value!r}.", fg="red")
        raise typer.Exit(code=1)
    return value


def models_from_flags(
    *,
    attack_model: str | None = None,
    attack_base_url: str | None = None,
    attack_key_secret: str | None = None,
    analysis_model: str | None = None,
    analysis_base_url: str | None = None,
    analysis_key_secret: str | None = None,
    safety_model: str | None = None,
) -> dict[str, dict[str, str]] | None:
    """Collect the per-group model flags into a ``WarGameModels`` payload, or ``None`` if none were given.

    Only the fields the user actually set appear, so an omitted flag leaves that group's stored value (or
    iron-swarm's built-in default) in force. ``safety`` takes a model only: iron-swarm pins the guardrail
    LLM's endpoint and key when it writes the guardrail, so a base URL or secret there would never be read.
    """
    groups = {
        "attack": {"model": attack_model, "base_url": attack_base_url, "api_key_secret": attack_key_secret},
        "analysis": {"model": analysis_model, "base_url": analysis_base_url, "api_key_secret": analysis_key_secret},
        "safety": {"model": safety_model},
    }
    chosen = {
        group: {field: value for field, value in fields.items() if value is not None}
        for group, fields in groups.items()
    }
    selected = {group: fields for group, fields in chosen.items() if fields}
    return selected or None


def merge_models(stored: Any, chosen: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Overlay *chosen* onto the manifest's stored models, field by field within each group.

    ``PATCH /manifests`` replaces ``models`` wholesale, so setting one group without merging first would
    silently clear the others. Studio never hits this (its "save as default" always sends every group);
    a CLI flag naturally sets one thing at a time, so the merge happens here.
    """
    merged = {group: dict(fields) for group, fields in (stored or {}).items() if isinstance(fields, dict)}
    for group, fields in chosen.items():
        merged[group] = {**merged.get(group, {}), **fields}
    return merged


def validated_defenders(values: list[str]) -> list[str] | None:
    """Reject unknown defender keys, which the job would otherwise read as 'use every default'."""
    if not values:
        return None
    unknown = [value for value in values if value not in DEFENDER_ENTRIES]
    if unknown:
        choices = ", ".join(sorted(DEFENDER_ENTRIES))
        typer.secho(f"Error: unknown defender {', '.join(unknown)!r}; choose from {choices}.", fg="red")
        raise typer.Exit(code=1)
    return list(values)
