# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Code generation utilities for the NeMo CLI."""

from __future__ import annotations

import json
from textwrap import dedent
from typing import Any

from nemo_platform_ext.cli.core.context import CLIContext


def handle_code_generation(
    resource_path: list[str],
    method: str,
    sdk_kwargs: dict[str, Any],
    output_format: str,
    context: CLIContext,
    wait_config: dict[str, Any] | None = None,
    wait_options: dict[str, Any] | None = None,
) -> bool:
    """
    Check if in code generation mode and generate code if needed.

    Args:
        resource_path: Path to the resource (e.g., ["models"], ["customization", "configs"])
        method: Method name (e.g., "list", "create", "retrieve")
        sdk_kwargs: Arguments to pass to the SDK method
        output_format: Output format

    Returns:
        True if code was generated (don't execute command), False otherwise
    """
    if output_format == "code":
        base_url = context.get_base_url("http://localhost:8080")
        code = generate_python_code(
            resource_path=resource_path,
            method=method,
            args=sdk_kwargs,
            base_url=base_url,
            wait_config=wait_config,
            wait_options=wait_options,
        )
        formatted_code = format_code_output(code, language="python")
        print(formatted_code)
        return True

    return False


def generate_python_code(
    resource_path: list[str],
    method: str,
    args: dict[str, Any],
    base_url: str | None = None,
    wait_config: dict[str, Any] | None = None,
    wait_options: dict[str, Any] | None = None,
) -> str:
    """
    Generate Python SDK code equivalent to a CLI command.

    Args:
        resource_path: Path to the resource (e.g., ["models"], ["customization", "configs"])
        method: Method name (e.g., "list", "create", "retrieve")
        args: Dictionary of arguments to pass to the method
        base_url: Base URL for the client (if specified)

    Returns:
        Python code string
    """
    lines = []

    wait_type = wait_config.get("type") if wait_config else None

    if wait_config:
        lines.append("import time")
    if wait_type == "inference_deployment":
        lines.append(
            "from nemo_platform_plugin.client.client import NemoClient\nfrom nemo_platform_plugin.client.errors import NemoHTTPError as APIStatusError, NemoTransportError as APIConnectionError, NemoTransportError as APITimeoutError, NotFoundError"
        )
    else:
        lines.append("from nemo_platform_plugin.client.client import NemoClient")
    lines.append("")

    if base_url:
        lines.append(f"client = NeMoPlatform(base_url={_format_python_literal(base_url)})")
    else:
        lines.append("client = NemoClient()")
    lines.append("")

    resource_chain = "client." + ".".join(resource_path)
    _append_method_call(lines, resource_chain, method, _format_method_args(args))

    if wait_config:
        lines.extend(["", _render_wait_code(resource_path, args, wait_config, wait_options or {})])

    lines.append("")
    lines.append("print(response)")

    return "\n".join(lines)


def _format_method_args(args: dict[str, Any]) -> list[str]:
    return [f"{key}={_format_python_literal(value)}" for key, value in args.items() if value is not None]


def _append_method_call(lines: list[str], resource_chain: str, method: str, formatted_args: list[str]) -> None:
    if not formatted_args:
        lines.append(f"response = {resource_chain}.{method}()")
        return

    if len(formatted_args) <= 3 and all(len(arg) <= 40 for arg in formatted_args):
        lines.append(f"response = {resource_chain}.{method}({', '.join(formatted_args)})")
        return

    lines.append(f"response = {resource_chain}.{method}(")
    for i, arg in enumerate(formatted_args):
        comma = "," if i < len(formatted_args) - 1 else ""
        lines.append(f"    {arg}{comma}")
    lines.append(")")


def _format_keyword_args(args: dict[str, Any], keys: list[str]) -> str:
    formatted_args = []
    for key in keys:
        value = args.get(key)
        if value is None:
            continue
        formatted_args.append(f"{key}={_format_python_literal(value)}")
    return ", " + ", ".join(formatted_args) if formatted_args else ""


def _format_python_literal(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    return repr(value)


def _render_wait_code(
    resource_path: list[str],
    args: dict[str, Any],
    wait_config: dict[str, Any],
    wait_options: dict[str, Any],
) -> str:
    wait_type = wait_config.get("type")
    resource_label = str(wait_config.get("resource_label") or "resource")
    timeout = wait_options.get("timeout", 1200)
    poll_interval = wait_options.get("poll_interval", 3)
    resource_chain = "client." + ".".join(resource_path)
    status_kwargs = _format_keyword_args(args, ["workspace"])
    resource_name = 'getattr(response, "name", None)'
    if args.get("name") is not None:
        resource_name = f"{resource_name} or {_format_python_literal(args['name'])}"

    prelude = dedent(
        f"""
        resource_name = {resource_name}
        if not resource_name:
            raise RuntimeError("Unable to determine created resource name for --wait")
        deadline = time.monotonic() + {timeout}
        """
    ).strip()

    if wait_type == "inference_deployment":
        workspace_literal = _format_python_literal(args["workspace"]) if args.get("workspace") is not None else "None"
        return "\n\n".join(
            [
                prelude,
                _render_inference_deployment_wait_code(
                    resource_chain,
                    status_kwargs,
                    workspace_literal,
                    poll_interval,
                ),
            ]
        )

    if wait_type == "platform_job":
        return "\n\n".join(
            [
                prelude,
                _render_platform_job_wait_code(resource_chain, status_kwargs, resource_label, poll_interval),
            ]
        )

    raise ValueError(f"Unsupported wait config type: {wait_type!r}")


def _render_inference_deployment_wait_code(
    resource_chain: str,
    status_kwargs: str,
    workspace_literal: str,
    poll_interval: int,
) -> str:
    return dedent(
        f"""
        while True:
            deployment = {resource_chain}.retrieve(resource_name{status_kwargs})
            history = getattr(deployment, "status_history", None)
            status = history[-1].status if history else deployment.status
            if status == "READY":
                response = deployment
                provider_name = resource_name
                provider_workspace = {workspace_literal}
                model_provider_id = getattr(deployment, "model_provider_id", None)
                if model_provider_id:
                    provider_workspace, _, provider_name = model_provider_id.partition("/")
                    if not provider_workspace or not provider_name:
                        provider_workspace = {workspace_literal}
                        provider_name = resource_name
                break
            if status in {{"ERROR", "LOST"}}:
                raise RuntimeError(f"Deployment {{resource_name!r}} ended with status {{status!r}}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for deployment {{resource_name!r}} to become READY")
            time.sleep(min({poll_interval}, remaining))

        while True:
            try:
                if provider_workspace is None:
                    client.inference.gateway.provider.ready(provider_name)
                else:
                    client.inference.gateway.provider.ready(provider_name, workspace=provider_workspace)
                break
            except NotFoundError:
                pass
            except (APIConnectionError, APITimeoutError):
                pass
            except APIStatusError as exc:
                if exc.status_code not in {{429, 502, 503, 504}}:
                    raise
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for gateway readiness for {{resource_name!r}}")
            time.sleep(min({poll_interval}, remaining))
        """
    ).strip()


def _render_platform_job_wait_code(
    resource_chain: str,
    status_kwargs: str,
    resource_label: str,
    poll_interval: int,
) -> str:
    resource_label_literal = _format_python_literal(resource_label)

    return dedent(
        f"""
        while True:
            status_response = {resource_chain}.get_status(resource_name{status_kwargs})
            status = str(status_response.status or "").lower()
            if status == "completed":
                response = status_response
                break
            if status in {{"cancelled", "error"}}:
                raise RuntimeError(
                    {resource_label_literal} + f" {{resource_name!r}} ended with status {{status!r}}"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Timed out waiting for "
                    + {resource_label_literal}
                    + f" {{resource_name!r}} to complete"
                )
            time.sleep(min({poll_interval}, remaining))
        """
    ).strip()


def format_code_output(code: str, language: str = "python") -> str:
    """
    Format code output with syntax highlighting.

    Args:
        code: Code string to format
        language: Programming language

    Returns:
        Formatted code string
    """
    from rich.console import Console
    from rich.syntax import Syntax

    from nemo_platform_ext.cli.core.api import is_tty

    if not is_tty():
        return code

    console = Console()
    syntax = Syntax(
        code,
        language,
        line_numbers=False,
        background_color="black",
        padding=(1, 2),
    )

    with console.capture() as capture:
        console.print(syntax)

    return capture.get()
