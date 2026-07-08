# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""CLI bridge to ``scripts/nat_to_fabric.py``."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import typer

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = _PLUGIN_ROOT / "scripts" / "nat_to_fabric.py"


def _load_nat_to_fabric_module():
    spec = importlib.util.spec_from_file_location("nemo_optimization_scripts.nat_to_fabric", _SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load nat_to_fabric script at {_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


convert_app = typer.Typer(
    name="convert",
    help="Convert legacy NAT optimize/workflow YAML to Fabric-native packages.",
    no_args_is_help=True,
)


@convert_app.command("nat-to-fabric")
def nat_to_fabric(
    input: Path = typer.Argument(..., exists=True, dir_okay=False, help="Legacy NAT YAML file."),
    output: Path = typer.Argument(..., dir_okay=False, help="Output Fabric-native YAML path."),
    agent_name: str | None = typer.Option(None, "--agent-name", help="Fabric metadata.name override."),
    fabric_base_dir: Path | None = typer.Option(
        None,
        "--fabric-base-dir",
        help="eval.fabric.base_dir for FabricAgentRuntime (NeMo-Fabric example checkout).",
    ),
    capture_trajectory: bool | None = typer.Option(
        None,
        "--capture-trajectory/--no-capture-trajectory",
        help="Set eval.fabric.capture_trajectory explicitly.",
    ),
) -> None:
    """Migrate NAT workflow/optimize YAML off the hot path."""
    script = _load_nat_to_fabric_module()
    try:
        script.convert_nat_file(
            input,
            output,
            agent_name=agent_name,
            fabric_base_dir=fabric_base_dir,
            capture_trajectory=capture_trajectory,
        )
    except script.NatToFabricError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Wrote Fabric-native config to {output}")
