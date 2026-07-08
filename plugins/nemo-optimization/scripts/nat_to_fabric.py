#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""One-time migration helper: legacy NAT optimize/workflow YAML → Fabric-native packages.

Usage::

    python scripts/nat_to_fabric.py input.yml output.yml \\
        --agent-name react-optimize \\
        --fabric-base-dir /path/to/NeMo-Fabric/examples/react-optimize-agent

Or via the customization CLI::

    nemo customization optimize convert nat-to-fabric input.yml output.yml
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import typer
import yaml

from nemo_optimization.fabric import FABRIC_AGENT_SCHEMA_VERSION, is_fabric_agent_config, looks_like_nat_config

NAT_WORKFLOW_REACT = "react_agent"
FABRIC_LANGCHAIN_REACT = "nvidia.fabric.langchain.react"

_DEFAULT_LLM_KEYS = frozenset({"llm", "default"})
_TUNABLE_RAG_TYPES = frozenset({"tunable_rag_evaluator", "tunable-rag-evaluator"})


class NatToFabricError(ValueError):
    """Raised when a NAT config cannot be converted."""


def convert_nat_to_fabric(
    config: Mapping[str, Any],
    *,
    agent_name: str | None = None,
    fabric_base_dir: str | Path | None = None,
    fabric_profiles: Sequence[Mapping[str, Any]] | None = None,
    capture_trajectory: bool | None = None,
) -> dict[str, Any]:
    """Convert a legacy NAT YAML mapping to a Fabric-native package."""
    if is_fabric_agent_config(config):
        return copy.deepcopy(dict(config))

    if not looks_like_nat_config(config):
        raise NatToFabricError(
            "Input does not look like legacy NAT workflow YAML or a Fabric agent package. "
            f"Expected keys such as workflow/llms or schema_version {FABRIC_AGENT_SCHEMA_VERSION!r}."
        )

    payload: dict[str, Any] = {}
    if isinstance(config.get("workflow"), Mapping):
        payload = convert_nat_workflow_agent(config, agent_name=agent_name)
    else:
        payload = {
            "schema_version": FABRIC_AGENT_SCHEMA_VERSION,
            "metadata": {"name": agent_name or _infer_name(config)},
        }

    if isinstance(config.get("models"), Mapping):
        payload["models"] = copy.deepcopy(dict(config["models"]))
    elif isinstance(config.get("llms"), Mapping):
        payload["models"] = convert_nat_llms_to_models(config["llms"], workflow=config.get("workflow"))

    if isinstance(config.get("eval"), Mapping):
        payload["eval"] = convert_nat_eval(
            config["eval"],
            llm_name_map=_llm_name_map(config.get("llms"), workflow=config.get("workflow")),
            fabric_base_dir=fabric_base_dir,
            fabric_profiles=fabric_profiles,
            capture_trajectory=capture_trajectory,
        )

    if isinstance(config.get("optimizer"), Mapping):
        payload["optimizer"] = convert_nat_optimizer(
            config["optimizer"],
            llms=config.get("llms"),
            workflow=config.get("workflow"),
        )
    elif not isinstance(config.get("workflow"), Mapping):
        raise NatToFabricError("NAT optimize config must declare an optimizer section.")

    return payload


def convert_nat_workflow_agent(config: Mapping[str, Any], *, agent_name: str | None = None) -> dict[str, Any]:
    """Map a NAT workflow package (react_agent) to ``fabric.agent/v1alpha1``."""
    workflow = config.get("workflow")
    if not isinstance(workflow, Mapping):
        raise NatToFabricError("NAT agent config must include a workflow mapping.")
    if str(workflow.get("_type")) != NAT_WORKFLOW_REACT:
        raise NatToFabricError(
            f"Unsupported NAT workflow type {workflow.get('_type')!r}. "
            f"Only {NAT_WORKFLOW_REACT!r} is supported by nat_to_fabric."
        )

    llms = config.get("llms")
    if not isinstance(llms, Mapping) or not llms:
        raise NatToFabricError("NAT react_agent config must declare llms.")

    llm_name_map = _llm_name_map(llms, workflow=workflow)
    workflow_llm = str(workflow.get("llm_name") or "llm")
    fabric_llm_name = llm_name_map.get(workflow_llm, "default")

    return {
        "schema_version": FABRIC_AGENT_SCHEMA_VERSION,
        "metadata": {
            "name": agent_name or _infer_name(config),
            "description": "Converted from legacy NAT react_agent workflow.",
        },
        "harness": {
            "adapter_id": FABRIC_LANGCHAIN_REACT,
            "resolution": "preinstalled",
            "settings": {
                "workflow": _convert_workflow_settings(workflow, fabric_llm_name=fabric_llm_name),
                "tools": _convert_tools(config),
            },
        },
        "models": convert_nat_llms_to_models(llms, workflow=workflow),
        "runtime": {
            "mode": "oneshot",
            "transport": "library",
            "input_schema": "text",
            "output_schema": "message",
        },
        "environment": {"provider": "local", "workspace": "."},
        "telemetry": {"enabled": False},
    }


def convert_nat_llms_to_models(
    llms: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert NAT ``llms`` entries to Fabric ``models``."""
    name_map = _llm_name_map(llms, workflow=workflow)
    models: dict[str, Any] = {}
    for nat_name, raw in llms.items():
        if not isinstance(raw, Mapping):
            continue
        fabric_name = name_map.get(str(nat_name), str(nat_name))
        models[fabric_name] = _convert_llm_entry(raw)
    return models


def convert_nat_eval(
    eval_config: Mapping[str, Any],
    *,
    llm_name_map: Mapping[str, str],
    fabric_base_dir: str | Path | None = None,
    fabric_profiles: Sequence[Mapping[str, Any]] | None = None,
    capture_trajectory: bool | None = None,
) -> dict[str, Any]:
    """Convert NAT eval config; add Fabric runtime hints when requested."""
    converted = copy.deepcopy(dict(eval_config))
    evaluators = converted.get("evaluators")
    if isinstance(evaluators, Mapping):
        for evaluator in evaluators.values():
            if not isinstance(evaluator, Mapping):
                continue
            llm_name = evaluator.get("llm_name")
            if isinstance(llm_name, str) and llm_name in llm_name_map:
                evaluator["llm_name"] = llm_name_map[llm_name]
            evaluator_type = evaluator.get("_type") or evaluator.get("type")
            if evaluator_type in _TUNABLE_RAG_TYPES:
                evaluator["_type"] = "tunable_rag_evaluator"

    fabric: dict[str, Any] = {}
    if isinstance(converted.get("fabric"), Mapping):
        fabric.update(copy.deepcopy(dict(converted["fabric"])))
    if fabric_base_dir is not None:
        fabric["base_dir"] = str(Path(fabric_base_dir).expanduser())
    if fabric_profiles is not None:
        fabric["profiles"] = [copy.deepcopy(dict(profile)) for profile in fabric_profiles]
    if capture_trajectory is not None:
        fabric["capture_trajectory"] = capture_trajectory
    if fabric:
        converted["fabric"] = fabric
    return converted


def convert_nat_optimizer(
    optimizer: Mapping[str, Any],
    *,
    llms: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert NAT optimizer block, flattening per-LLM search spaces to Fabric dotted paths."""
    converted = copy.deepcopy(dict(optimizer))
    llm_name_map = _llm_name_map(llms or {}, workflow=workflow)

    search_space: dict[str, Any] = {}
    if isinstance(converted.get("search_space"), Mapping):
        for key, spec in converted["search_space"].items():
            search_space[_rewrite_search_space_key(str(key), llm_name_map)] = spec

    if isinstance(llms, Mapping):
        for nat_llm_name, llm_cfg in llms.items():
            if not isinstance(llm_cfg, Mapping):
                continue
            params = llm_cfg.get("optimizable_params")
            spaces = llm_cfg.get("search_space")
            if not isinstance(params, Sequence) or not isinstance(spaces, Mapping):
                continue
            fabric_llm = llm_name_map.get(str(nat_llm_name), str(nat_llm_name))
            for param in params:
                param_name = str(param)
                if param_name not in spaces:
                    continue
                search_space[f"models.{fabric_llm}.{param_name}"] = copy.deepcopy(spaces[param_name])

    if search_space:
        converted["search_space"] = search_space
    converted.pop("optimizable_params", None)

    if isinstance(converted.get("eval_metrics"), Mapping):
        for metric_name, metric_cfg in converted["eval_metrics"].items():
            if not isinstance(metric_cfg, Mapping):
                continue
            evaluator_name = metric_cfg.get("evaluator_name")
            if evaluator_name in (None, metric_name, "accuracy"):
                metric_cfg["evaluator_name"] = "average_score"

    return converted


def convert_nat_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    agent_name: str | None = None,
    fabric_base_dir: str | Path | None = None,
    fabric_profiles: Sequence[Mapping[str, Any]] | None = None,
    capture_trajectory: bool | None = None,
) -> dict[str, Any]:
    """Load NAT YAML, convert, and write Fabric-native YAML to *output_path*."""
    input_path = Path(input_path).expanduser()
    output_path = Path(output_path).expanduser()
    raw = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise NatToFabricError(f"Expected a YAML mapping in {input_path}")

    converted = convert_nat_to_fabric(
        raw,
        agent_name=agent_name,
        fabric_base_dir=fabric_base_dir,
        fabric_profiles=fabric_profiles,
        capture_trajectory=capture_trajectory,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.safe_dump(converted, sort_keys=False), encoding="utf-8")
    return converted


def _convert_workflow_settings(workflow: Mapping[str, Any], *, fabric_llm_name: str) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "tool_names": list(workflow.get("tool_names") or []),
        "llm_name": fabric_llm_name,
        "verbose": bool(workflow.get("verbose", False)),
        "parse_agent_response_max_retries": int(workflow.get("parse_agent_response_max_retries", 3)),
        "max_tool_calls": int(workflow.get("max_tool_calls", 15)),
        "use_native_tool_calling": bool(workflow.get("use_native_tool_calling", False)),
    }
    if workflow.get("max_history") is not None:
        settings["max_history"] = workflow["max_history"]
    return settings


def _convert_tools(config: Mapping[str, Any]) -> dict[str, Any]:
    tools: dict[str, Any] = {}
    functions = config.get("functions")
    if isinstance(functions, Mapping):
        for name, raw in functions.items():
            if not isinstance(raw, Mapping):
                continue
            kind = str(raw.get("_type") or raw.get("type") or name)
            tool_cfg: dict[str, Any] = {"kind": _fabric_tool_kind(kind)}
            for key in ("max_results",):
                if key in raw:
                    tool_cfg[key] = raw[key]
            tools[str(name)] = tool_cfg

    function_groups = config.get("function_groups")
    if isinstance(function_groups, Mapping):
        for name, raw in function_groups.items():
            if not isinstance(raw, Mapping):
                continue
            group_type = str(raw.get("_type") or raw.get("type") or name)
            tool_cfg: dict[str, Any] = {"kind": "function_group"}
            if group_type == "calculator":
                tool_cfg["include"] = ["add", "subtract", "multiply", "divide", "compare"]
            tools[str(name)] = tool_cfg

    return tools


def _fabric_tool_kind(nat_type: str) -> str:
    mapping = {
        "wiki_search": "wiki_search",
        "current_datetime": "current_datetime",
    }
    return mapping.get(nat_type, nat_type)


def _convert_llm_entry(raw: Mapping[str, Any]) -> dict[str, Any]:
    provider = str(raw.get("_type") or raw.get("provider") or "openai").lower()
    model_name = raw.get("model_name") or raw.get("model")
    converted: dict[str, Any] = {
        "provider": provider,
        "model": model_name,
    }
    for key in ("temperature", "top_p", "max_tokens", "base_url", "url"):
        if key in raw:
            converted[key] = raw[key]
    api_key = raw.get("api_key")
    if api_key is not None:
        converted["api_key"] = api_key
        if str(api_key) == "not-used":
            converted["allow_empty_api_key"] = True
    if raw.get("api_key_env"):
        converted["api_key_env"] = raw["api_key_env"]
    return converted


def _llm_name_map(llms: Mapping[str, Any], *, workflow: Mapping[str, Any] | None) -> dict[str, str]:
    mapping: dict[str, str] = {}
    workflow_llm = None
    if isinstance(workflow, Mapping):
        workflow_llm = str(workflow.get("llm_name") or "llm")
    for nat_name in llms:
        name = str(nat_name)
        if workflow_llm is not None and name == workflow_llm:
            mapping[name] = "default"
        elif name in _DEFAULT_LLM_KEYS:
            mapping[name] = "default"
        elif name.endswith("_llm"):
            mapping[name] = name[: -len("_llm")]
        else:
            mapping[name] = name
    return mapping


def _rewrite_search_space_key(key: str, llm_name_map: Mapping[str, str]) -> str:
    if not key.startswith("llms."):
        return key
    parts = key.split(".")
    if len(parts) < 3:
        return key
    fabric_llm = llm_name_map.get(parts[1], parts[1])
    return f"models.{fabric_llm}.{'.'.join(parts[2:])}"


def _infer_name(config: Mapping[str, Any]) -> str:
    general = config.get("general")
    if isinstance(general, Mapping):
        for key in ("name", "agent_name"):
            value = general.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    metadata = config.get("metadata")
    if isinstance(metadata, Mapping):
        value = metadata.get("name")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "converted-agent"


app = typer.Typer(
    name="nat_to_fabric",
    help="Convert legacy NAT optimize/workflow YAML to Fabric-native packages.",
    no_args_is_help=True,
)


@app.command()
def main(
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
    """Migrate NAT workflow/optimize YAML off the optimize hot path."""
    try:
        convert_nat_file(
            input,
            output,
            agent_name=agent_name,
            fabric_base_dir=fabric_base_dir,
            capture_trajectory=capture_trajectory,
        )
    except NatToFabricError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Wrote Fabric-native config to {output}")


if __name__ == "__main__":
    app()
