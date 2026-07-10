#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Fabric MVP spike helper for Platform-owned agent configuration.

This script exercises the proposed NeMo Agents flow where Platform reads its own
agent YAML, resolves defaults and harness variants, translates that shape into a
typed FabricConfig, then validates and runs it through the Fabric SDK. It covers
local Fabric dependency setup plus plan, doctor, one-shot, and multi-turn runtime
paths for Hermes and Codex harnesses.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from nemo_fabric import Fabric, FabricConfig, RunResult

REPO_ROOT = Path(__file__).resolve().parents[4]
EXAMPLE_DIR = Path(__file__).resolve().parent
PLATFORM_CONFIG_YAML = EXAMPLE_DIR / "agent.yaml"
DEFAULT_FABRIC_REPO = Path.home() / "workspace" / "NeMo-Fabric"
FABRIC_EXTRAS = ("codex", "hermes", "relay", "runtime")

HARNESS_ADAPTERS = {
    "codex": "nvidia.fabric.codex.cli",
    "hermes": "nvidia.fabric.hermes.sdk",
}


def project_python(repo_root: Path) -> Path:
    python = repo_root / ".venv" / "bin" / "python"
    if not python.exists():
        raise SystemExit(f"Project venv not found at {python}. Run `make bootstrap-python` from the repo root first.")
    return python


def fabric_repo() -> Path:
    return Path(os.environ.get("NEMO_FABRIC_REPO", DEFAULT_FABRIC_REPO)).expanduser()


def run_command(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, check=True)


def configure_adapter_python(repo_root: Path) -> None:
    python = project_python(repo_root)
    os.environ.setdefault("ADAPTER_PYTHON", str(python))
    os.environ["PATH"] = f"{python.parent}{os.pathsep}{os.environ['PATH']}"


def install_deps(repo_root: Path) -> None:
    python = project_python(repo_root)
    fabric = fabric_repo()
    if not fabric.is_dir():
        raise SystemExit(
            f"NeMo-Fabric checkout not found at {fabric}. Clone it or set NEMO_FABRIC_REPO=/path/to/NeMo-Fabric."
        )

    extras = ",".join(FABRIC_EXTRAS)
    run_command(
        ["uv", "pip", "install", "--python", str(python), f"{fabric}[{extras}]"],
        cwd=repo_root,
    )

    run_command(
        [
            str(python),
            "-c",
            (
                "import nemo_fabric; "
                "from nemo_fabric import Fabric, FabricConfig; "
                "import nemo_fabric_adapters.codex_cli; "
                "import nemo_fabric_adapters.hermes_sdk; "
                "import nemo_fabric_adapters.hermes_cli; "
                "print('nemo_fabric OK:', nemo_fabric.__file__)"
            ),
        ],
        cwd=repo_root,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fabric MVP spike helper")
    parser.add_argument(
        "command",
        choices=("install-deps", "run", "run-one-shot", "run-runtime"),
        help="Spike step to run.",
    )
    parser.add_argument(
        "--harness",
        help="Optional Platform harness variant to translate instead of default_harness.",
    )
    parser.add_argument(
        "--input",
        default="Hello from the NeMo Agents Fabric MVP spike.",
        help="Input text for one-shot Fabric invocation.",
    )
    parser.add_argument(
        "--second-input",
        default="What did I ask you to help with? Reply in one short sentence.",
        help="Second input text for multi-turn runtime invocation.",
    )
    parser.add_argument(
        "--enable-relay-telemetry",
        action="store_true",
        help="Enable Relay telemetry and inspect the generated ATIF/ATOF files.",
    )
    return parser.parse_args()


def load_platform_config(path_to_yaml: Path) -> dict[str, Any]:
    with path_to_yaml.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def select_harness(
    platform_config: dict[str, Any],
    harness_name: str | None,
) -> dict[str, Any]:
    selected_harness = harness_name or platform_config["default_harness"]
    harnesses = platform_config["harnesses"]

    if selected_harness not in harnesses:
        available = ", ".join(harnesses)
        raise ValueError(f"Unknown configured harness '{selected_harness}'. Configured harnesses: {available}")

    return harnesses[selected_harness]


def fabric_adapter_id(harness: dict[str, Any]) -> str:
    kind = harness["kind"]
    if kind not in HARNESS_ADAPTERS:
        available = ", ".join(HARNESS_ADAPTERS)
        raise ValueError(f"Unsupported harness kind '{kind}'. Supported harness kinds: {available}")
    return HARNESS_ADAPTERS[kind]


def relay_observability_config(platform_config: dict[str, Any]) -> dict[str, Any]:
    telemetry = platform_config.get("telemetry", {})
    output_dir = telemetry.get("output_dir", "./artifacts/relay")
    atif = telemetry.get("atif", {})
    atof = telemetry.get("atof", {})

    return {
        "version": 1,
        "components": [
            {
                "kind": "observability",
                "enabled": True,
                "config": {
                    "version": 1,
                    "atif": {
                        "enabled": atif.get("enabled", True),
                        "output_directory": output_dir,
                        "filename_template": atif.get("filename_template", "trajectory-{session_id}.atif.json"),
                        "agent_name": platform_config["name"],
                        "agent_version": platform_config.get("version", "fabric-mvp-spike"),
                    },
                    "atof": {
                        "enabled": atof.get("enabled", True),
                        "output_directory": output_dir,
                        "filename": atof.get("filename", "events.atof.jsonl"),
                        "mode": atof.get("mode", "overwrite"),
                    },
                },
            }
        ],
    }


def apply_relay_telemetry(
    fabric_config: FabricConfig,
    platform_config: dict[str, Any],
    *,
    force_enable: bool,
) -> FabricConfig:
    telemetry = platform_config.get("telemetry", {})
    if not (force_enable or telemetry.get("enabled", False)):
        return fabric_config

    provider = telemetry.get("provider", "relay")
    if provider != "relay":
        raise ValueError(f"Unsupported telemetry provider '{provider}'. This spike only validates Relay telemetry.")

    fabric_config.enable_relay(
        project=telemetry.get("project"),
        output_dir=telemetry.get("output_dir", "./artifacts/relay"),
        config=relay_observability_config(platform_config),
    )
    return fabric_config


def platform_config_translator(
    path_to_yaml: Path,
    harness_name: str | None = None,
    *,
    enable_relay_telemetry: bool = False,
) -> FabricConfig:
    from nemo_fabric import (
        EnvironmentConfig,
        FabricConfig,
        HarnessConfig,
        MetadataConfig,
        ModelConfig,
    )

    platform_config = load_platform_config(path_to_yaml)
    harness = select_harness(platform_config, harness_name)
    model_config = harness.get("model") or platform_config["models"]["default"]

    fabric_config = FabricConfig(
        metadata=MetadataConfig(
            name=platform_config["name"],
            description=platform_config.get("description"),
        ),
        harness=HarnessConfig(
            adapter_id=fabric_adapter_id(harness),
            resolution="preinstalled",
            settings=harness.get("settings", {}),
        ),
        models={
            "default": ModelConfig(**model_config),
        },
        environment=EnvironmentConfig(
            provider="local",
            workspace=platform_config.get("environment", {}).get("workspace"),
            artifacts=platform_config.get("environment", {}).get("artifacts"),
        ),
    )
    return apply_relay_telemetry(
        fabric_config,
        platform_config,
        force_enable=enable_relay_telemetry,
    )


def validate_preflight_report(preflight_report: dict[str, Any]) -> None:
    status = preflight_report.get("status")
    if status == "pass":
        return

    failed_messages: list[str] = []

    for check in preflight_report.get("checks", []):
        check_status = check.get("status")
        if check_status == "pass":
            continue

        name = check.get("name", "unknown")
        message = check.get("message", "No diagnostic message provided.")
        failed_messages.append(f"- {name}: {check_status} - {message}")

    if not failed_messages:
        failed_messages.append("- No failing subsection was reported.")

    details = "\n".join(failed_messages)
    raise SystemExit(f"Fabric preflight failed with status: {status}\n\n{details}")


def ensure_local_environment_dirs(fabric_config: FabricConfig, base_dir: Path) -> None:
    environment = fabric_config.environment
    if environment is None or environment.provider != "local":
        return

    for value in (environment.workspace, environment.artifacts):
        if value is None:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = base_dir / path
        path.mkdir(parents=True, exist_ok=True)

    telemetry = fabric_config.telemetry
    if telemetry is not None and telemetry.output_dir is not None:
        output_dir = Path(telemetry.output_dir)
        if not output_dir.is_absolute():
            output_dir = base_dir / output_dir
        output_dir.mkdir(parents=True, exist_ok=True)


def relay_telemetry_files(fabric_config: FabricConfig, base_dir: Path) -> dict[str, Any]:
    telemetry = fabric_config.telemetry
    if telemetry is None or not telemetry.output_dir:
        return {"enabled": False, "files": []}

    output_dir = Path(telemetry.output_dir)
    if not output_dir.is_absolute():
        output_dir = base_dir / output_dir

    files = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        files.append(
            {
                "path": str(path),
                "relative_path": str(path.relative_to(output_dir)),
                "size_bytes": path.stat().st_size,
            }
        )

    return {
        "enabled": telemetry.enabled,
        "provider": telemetry.provider,
        "project": telemetry.project,
        "output_dir": str(output_dir),
        "files": files,
    }


def summarize_run_result(run_result: dict[str, Any]) -> dict[str, Any]:
    output = run_result.get("output") or {}
    error = run_result.get("error")
    artifacts = run_result.get("artifacts") or {}

    return {
        "agent_name": run_result.get("agent_name"),
        "harness": run_result.get("harness"),
        "adapter_id": run_result.get("adapter_id"),
        "runtime_id": run_result.get("runtime_id"),
        "invocation_id": run_result.get("invocation_id"),
        "request_id": run_result.get("request_id"),
        "status": run_result.get("status"),
        "response": output.get("response") if isinstance(output, dict) else output,
        "error": (
            {
                "stage": error.get("stage"),
                "code": error.get("code"),
                "message": error.get("message"),
            }
            if isinstance(error, dict)
            else error
        ),
        "artifact_root": artifacts.get("root"),
        "artifacts": [
            {
                "name": artifact.get("name"),
                "kind": artifact.get("kind"),
                "path": artifact.get("path"),
                "media_type": artifact.get("media_type"),
            }
            for artifact in artifacts.get("artifacts", [])
        ],
        "telemetry": run_result.get("telemetry", []),
        "events": [
            {
                "kind": event.get("kind"),
                "message": event.get("message"),
            }
            for event in run_result.get("events", [])
        ],
        "metadata": run_result.get("metadata", {}),
    }


async def run_one_shot(
    fabric: Fabric,
    fabric_config: FabricConfig,
    *,
    input_text: str,
) -> RunResult:
    return await fabric.run(
        fabric_config,
        base_dir=EXAMPLE_DIR,
        input=input_text,
    )


async def run_multi_turn(
    fabric: Fabric,
    fabric_config: FabricConfig,
    *,
    first_input: str,
    second_input: str,
) -> dict[str, Any]:
    runtime = await fabric.start_runtime(
        fabric_config,
        base_dir=EXAMPLE_DIR,
    )
    runtime_result: dict[str, Any] | None = None
    try:
        first = await runtime.invoke(input=first_input)
        second = await runtime.invoke(input=second_input)

        runtime_result = {
            "runtime_id": runtime.runtime_id,
            "runtime_status_during_turns": runtime.status.value,
            "runtime_handle": runtime.handle.to_mapping(),
            "invocations": runtime.invocations,
            "messages": runtime.messages,
            "turns": [
                first.to_mapping(),
                second.to_mapping(),
            ],
        }
    finally:
        await runtime.stop()

    if runtime_result is None:
        raise RuntimeError("runtime stopped before any turn completed")

    runtime_result["runtime_status_after_stop"] = runtime.status.value
    return runtime_result


def prepare_fabric_run(
    fabric: Fabric,
    *,
    harness_name: str | None,
    enable_relay_telemetry: bool,
) -> FabricConfig:
    from nemo_fabric import FabricConfigError

    fabric_config = platform_config_translator(
        PLATFORM_CONFIG_YAML,
        harness_name,
        enable_relay_telemetry=enable_relay_telemetry,
    )
    ensure_local_environment_dirs(fabric_config, EXAMPLE_DIR)

    try:
        fabric.plan(fabric_config, base_dir=EXAMPLE_DIR)
    except FabricConfigError as e:
        raise SystemExit(f"Plan error: {e}") from e

    try:
        preflight = asyncio.run(fabric.doctor(fabric_config, base_dir=EXAMPLE_DIR))
        validate_preflight_report(preflight.to_mapping())
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"Doctor error: {e}") from e

    return fabric_config


def summarize_runtime_result(runtime_result: dict[str, Any]) -> dict[str, Any]:
    turns = runtime_result["turns"]
    runtime_id = runtime_result["runtime_id"]
    return {
        "runtime_id": runtime_id,
        "runtime_status_during_turns": runtime_result["runtime_status_during_turns"],
        "runtime_status_after_stop": runtime_result["runtime_status_after_stop"],
        "all_turns_used_same_runtime": all(turn.get("runtime_id") == runtime_id for turn in turns),
        "turn_count": len(turns),
        "turns": [
            {
                "turn": index,
                **summarize_run_result(turn),
            }
            for index, turn in enumerate(turns, start=1)
        ],
        "invocations": runtime_result["invocations"],
        "message_count": len(runtime_result["messages"]),
    }


def print_yaml_section(title: str, value: dict[str, Any]) -> None:
    print(f"# {title}")
    print(yaml.safe_dump(value, sort_keys=False))


def run_one_shot_command(args: argparse.Namespace) -> None:
    from nemo_fabric import Fabric, FabricRuntimeError

    configure_adapter_python(REPO_ROOT)
    fabric = Fabric()
    fabric_config = prepare_fabric_run(
        fabric,
        harness_name=args.harness,
        enable_relay_telemetry=args.enable_relay_telemetry,
    )

    try:
        result = asyncio.run(run_one_shot(fabric, fabric_config, input_text=args.input))
    except FabricRuntimeError as e:
        raise SystemExit(f"Run error: {e}") from e

    result_mapping = result.to_mapping()
    print_yaml_section("Platform result summary", summarize_run_result(result_mapping))
    print_yaml_section("Relay telemetry files", relay_telemetry_files(fabric_config, EXAMPLE_DIR))
    print_yaml_section("Raw Fabric RunResult", result_mapping)


def run_runtime_command(args: argparse.Namespace) -> None:
    from nemo_fabric import Fabric, FabricRuntimeError

    configure_adapter_python(REPO_ROOT)
    fabric = Fabric()
    fabric_config = prepare_fabric_run(
        fabric,
        harness_name=args.harness,
        enable_relay_telemetry=args.enable_relay_telemetry,
    )

    try:
        runtime_result = asyncio.run(
            run_multi_turn(
                fabric,
                fabric_config,
                first_input=args.input,
                second_input=args.second_input,
            )
        )
    except FabricRuntimeError as e:
        raise SystemExit(f"Runtime error: {e}") from e

    print_yaml_section("Platform runtime summary", summarize_runtime_result(runtime_result))
    print_yaml_section("Relay telemetry files", relay_telemetry_files(fabric_config, EXAMPLE_DIR))
    print_yaml_section("Raw Fabric Runtime Turns", runtime_result)


def main() -> None:
    args = parse_args()
    if args.command == "install-deps":
        install_deps(REPO_ROOT)
        return
    if args.command in ("run", "run-one-shot"):
        run_one_shot_command(args)
        return
    if args.command == "run-runtime":
        run_runtime_command(args)
        return


if __name__ == "__main__":
    main()
