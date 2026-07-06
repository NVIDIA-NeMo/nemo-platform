# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared wait helpers for CLI commands."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

from nemo_platform import APIConnectionError, APIStatusError, APITimeoutError, NotFoundError
from rich.console import Console
from rich.live import Live
from rich.text import Text

logger = logging.getLogger(__name__)
console = Console()

_TRANSIENT_GATEWAY_STATUS_CODES = {429, 502, 503, 504}


def _pause(seconds: float) -> None:
    time.sleep(seconds)


def _seconds_since_creation(entry_timestamp: datetime | str | None, created_at: datetime | None) -> int | None:
    if created_at is None or entry_timestamp is None:
        return None
    if isinstance(entry_timestamp, str):
        try:
            entry_timestamp = datetime.fromisoformat(entry_timestamp.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if not hasattr(entry_timestamp, "timestamp") or not hasattr(created_at, "timestamp"):
        return None
    try:
        return int(entry_timestamp.timestamp() - created_at.timestamp())
    except (TypeError, OSError):
        return None


def _status_text(status: Any) -> str:
    return str(status or "")


def _emit_job_run_event(job_status: Any, *, resource_label: str, status: str, start_time: float) -> None:
    """Emit a ``job_run`` telemetry event for a terminal platform job.

    Best effort: never raises and never affects the waiter's return value.
    """
    try:
        from nemo_platform_ext.cli.telemetry.emit import emit_event
        from nemo_platform_ext.cli.telemetry.events import JobRunEvent, TaskStatusEnum

        status_map = {
            "completed": TaskStatusEnum.COMPLETED,
            "error": TaskStatusEnum.ERROR,
            "cancelled": TaskStatusEnum.CANCELED,
        }
        task_status = status_map.get(status, TaskStatusEnum.UNDEFINED)

        details = getattr(job_status, "status_details", None)
        if not isinstance(details, dict):
            details = {}

        plugins: set[str] = set()
        for step in getattr(job_status, "steps", None) or []:
            step_name = getattr(step, "name", "") or ""
            prefix = step_name.split(".", 1)[0]
            if prefix:
                plugins.add(prefix)

        # ``status_details`` can carry an explicit null (e.g. ``model: null``). Passing
        # None to the str-typed / int-typed event fields fails validation and the
        # best-effort guard would silently drop the whole event, so coerce here.
        # Tokens use explicit None checks, not ``or``, so a legitimate 0 survives as 0.
        model = details.get("model") or "undefined"
        raw_input_tokens = details.get("input_tokens")
        input_tokens = int(raw_input_tokens) if raw_input_tokens is not None else -1
        raw_output_tokens = details.get("output_tokens")
        output_tokens = int(raw_output_tokens) if raw_output_tokens is not None else -1

        emit_event(
            JobRunEvent(
                task_status=task_status,
                job_type=resource_label,
                duration_sec=float(time.time() - start_time),
                plugins=sorted(plugins),
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )
    except Exception:
        logger.debug("Failed to emit job_run telemetry event", exc_info=True)


def _make_history_line(
    timestamp_str: str,
    seconds_since_creation: int | None,
    status: str,
    status_message: str = "",
) -> Text:
    text = Text()
    text.append(f"  [{timestamp_str}] ", style="dim")
    if seconds_since_creation is not None:
        text.append(f"(+{seconds_since_creation}s) ", style="dim")
    text.append("Status: ")
    text.append(status, style="cyan bold")
    if status_message:
        text.append(f" - {status_message}", style="dim")
    return text


def _make_live_display(
    polling_time: str,
    timeout: int,
    poll_interval: int,
    wait_elapsed: int,
) -> Text:
    text = Text()
    text.append("\n")
    text.append(
        f"Polling: {polling_time} | Timeout: {timeout}s | Poll interval: {poll_interval}s | Wait: {wait_elapsed}s",
        style="dim",
    )
    return text


def _sleep_until_next_poll(start_time: float, timeout: float, poll_interval: int) -> bool:
    if poll_interval <= 0:
        raise ValueError(f"_sleep_until_next_poll poll_interval must be greater than 0, got {poll_interval}")
    remaining = timeout - (time.time() - start_time)
    if remaining <= 0:
        return False
    _pause(min(poll_interval, remaining))
    return True


def _gateway_provider_ref(deployment: Any, fallback_name: str, fallback_workspace: str) -> tuple[str, str]:
    model_provider_id = getattr(deployment, "model_provider_id", None)
    if isinstance(model_provider_id, str):
        workspace, separator, provider_name = model_provider_id.partition("/")
        if separator and workspace and provider_name:
            return provider_name, workspace
    return fallback_name, fallback_workspace


def _print_transient_wait_error(live: Live, resource_label: str, error: Exception) -> None:
    live.stop()
    console.print(f"\n[yellow]Transient {resource_label} check failed: {error}[/yellow]")
    live.start()


def wait_for_inference_deployment(
    client: Any,
    name: str,
    *,
    workspace: str | None = None,
    status: str = "READY",
    timeout: int = 1200,
    poll_interval: int = 3,
    check_gateway: bool = True,
) -> bool:
    """Wait for an inference deployment to reach the requested status."""
    if workspace is None:
        workspace = client._get_workspace_path_param()

    start_time = time.time()
    last_history_len = 0
    last_status = ""
    last_message = ""

    console.print(f"[bold]Waiting for deployment '{name}' to reach status: {status}[/bold]\n")

    with Live(console=console, refresh_per_second=4, transient=True) as live:
        while time.time() - start_time < timeout:
            wait_elapsed = int(time.time() - start_time)
            polling_time = datetime.now().strftime("%H:%M:%S")
            live.update(_make_live_display(polling_time, timeout, poll_interval, wait_elapsed))

            try:
                deployment = client.inference.deployments.retrieve(name, workspace=workspace)
                history = getattr(deployment, "status_history", None)
                created_at = getattr(deployment, "created_at", None)
                if history and len(history) > 0:
                    last_entry = history[-1]
                    current_status = _status_text(getattr(last_entry, "status", getattr(deployment, "status", "")))
                    current_message = getattr(last_entry, "status_message", "") or ""
                else:
                    current_status = _status_text(getattr(deployment, "status", ""))
                    current_message = getattr(deployment, "status_message", "") or ""
                last_status = current_status
                last_message = current_message

                if history and len(history) > last_history_len:
                    live.stop()
                    if last_history_len == 0:
                        console.print()
                    for i in range(last_history_len, len(history)):
                        entry = history[i]
                        ts = getattr(entry, "timestamp", None)
                        ts_str = ts.strftime("%H:%M:%S") if hasattr(ts, "strftime") else str(ts) if ts else ""
                        st = _status_text(getattr(entry, "status", ""))
                        msg = getattr(entry, "status_message", "") or ""
                        secs = _seconds_since_creation(ts, created_at)
                        console.print(_make_history_line(ts_str, secs, st, msg))
                    last_history_len = len(history)
                    console.print()
                    live.start()

                live.update(_make_live_display(polling_time, timeout, poll_interval, wait_elapsed))

                if current_status == status and status != "DELETED":
                    live.stop()
                    console.print(f"\n[green]✓ Deployment reached {status} status![/green]")
                    if status == "READY" and check_gateway:
                        remaining_timeout = timeout - (time.time() - start_time)
                        if remaining_timeout <= 0:
                            console.print("\n[red]✗ Timeout before gateway readiness check could complete[/red]")
                            return False
                        provider_name, provider_workspace = _gateway_provider_ref(deployment, name, workspace)
                        return wait_for_gateway(
                            client,
                            provider_name,
                            provider_workspace,
                            timeout=remaining_timeout,
                            poll_interval=poll_interval,
                        )
                    return True

                if current_status in {"ERROR", "LOST"} and status not in {"ERROR", "LOST"}:
                    live.stop()
                    console.print(f"\n[red]✗ Deployment entered {current_status} state: {current_message}[/red]")
                    return False

            except NotFoundError:
                if status == "DELETED":
                    live.stop()
                    console.print(f"\n[green]✓ Deployment {status}![/green]")
                    return True
                live.stop()
                console.print("\n[red]✗ Deployment not found[/red]")
                return False
            except (APIConnectionError, APITimeoutError) as exc:
                _print_transient_wait_error(live, "deployment status", exc)
            except APIStatusError as exc:
                if exc.status_code not in _TRANSIENT_GATEWAY_STATUS_CODES:
                    raise
                _print_transient_wait_error(live, "deployment status", exc)

            if not _sleep_until_next_poll(start_time, timeout, poll_interval):
                break

    wait_elapsed = int(time.time() - start_time)
    detail = f"Last status: {last_status}"
    if last_message:
        detail += f" - {last_message}"
    console.print(f"\n[red]✗ Timeout after {wait_elapsed}s. {detail}[/red]")
    return False


def wait_for_platform_job(
    jobs_resource: Any,
    name: str,
    *,
    workspace: str | None = None,
    resource_label: str = "job",
    timeout: int = 1200,
    poll_interval: int = 3,
) -> bool:
    """Wait for a platform job resource to complete."""
    start_time = time.time()
    last_status = ""

    console.print(f"[bold]Waiting for {resource_label} '{name}' to complete[/bold]\n")

    with Live(console=console, refresh_per_second=4, transient=True) as live:
        while time.time() - start_time < timeout:
            wait_elapsed = int(time.time() - start_time)
            polling_time = datetime.now().strftime("%H:%M:%S")
            live.update(_make_live_display(polling_time, timeout, poll_interval, wait_elapsed))

            try:
                job_status = jobs_resource.get_status(name, workspace=workspace)
            except NotFoundError:
                live.stop()
                console.print(f"\n[red]✗ {resource_label.title()} not found[/red]")
                return False
            except (APIConnectionError, APITimeoutError) as exc:
                _print_transient_wait_error(live, f"{resource_label} status", exc)
                if not _sleep_until_next_poll(start_time, timeout, poll_interval):
                    break
                continue
            except APIStatusError as exc:
                if exc.status_code not in _TRANSIENT_GATEWAY_STATUS_CODES:
                    raise
                _print_transient_wait_error(live, f"{resource_label} status", exc)
                if not _sleep_until_next_poll(start_time, timeout, poll_interval):
                    break
                continue

            current_status = _status_text(getattr(job_status, "status", "")).lower()
            if current_status != last_status:
                live.stop()
                console.print(_make_history_line(polling_time, wait_elapsed, current_status))
                last_status = current_status
                console.print()
                live.start()

            if current_status == "completed":
                live.stop()
                _emit_job_run_event(
                    job_status, resource_label=resource_label, status=current_status, start_time=start_time
                )
                console.print(f"\n[green]✓ {resource_label.title()} completed![/green]")
                return True

            if current_status in {"cancelled", "error"}:
                live.stop()
                _emit_job_run_event(
                    job_status, resource_label=resource_label, status=current_status, start_time=start_time
                )
                console.print(f"\n[red]✗ {resource_label.title()} entered {current_status} state[/red]")
                return False

            if not _sleep_until_next_poll(start_time, timeout, poll_interval):
                break

    wait_elapsed = int(time.time() - start_time)
    detail = f"Last status: {last_status}" if last_status else "No status returned"
    console.print(f"\n[red]✗ Timeout after {wait_elapsed}s. {detail}[/red]")
    return False


def wait_for_gateway(
    client: Any,
    provider_name: str,
    workspace: str,
    timeout: float = 60,
    poll_interval: int = 1,
) -> bool:
    """Wait for the inference gateway to be able to route to a provider."""
    start_time = time.time()
    start_timestamp = datetime.now().strftime("%H:%M:%S")

    console.print(f"[bold]Waiting for gateway to be ready for provider '{provider_name}'[/bold]\n")

    def _make_gateway_display(polling_time: str, elapsed: int, status: str) -> Text:
        text = Text()
        text.append(f"Polling: {polling_time} | Timeout: {timeout}s | Poll interval: {poll_interval}s\n", style="dim")
        text.append(f"  [{start_timestamp}] ", style="dim")
        text.append(f"({elapsed}s) ", style="dim")
        text.append(status)
        return text

    with Live(console=console, refresh_per_second=4, transient=True) as live:
        while time.time() - start_time < timeout:
            elapsed = int(time.time() - start_time)
            polling_time = datetime.now().strftime("%H:%M:%S")
            live.update(_make_gateway_display(polling_time, elapsed, "Checking gateway..."))

            try:
                client.inference.gateway.provider.ready(provider_name, workspace=workspace)
                live.stop()
                console.print(f"  [{polling_time}] ({elapsed}s) [green]Gateway is ready![/green]")
                return True
            except NotFoundError:
                pass
            except (APIConnectionError, APITimeoutError):
                pass
            except APIStatusError as exc:
                if exc.status_code in _TRANSIENT_GATEWAY_STATUS_CODES:
                    pass
                else:
                    live.stop()
                    console.print(f"\n[red]✗ Gateway readiness failed: {exc}[/red]")
                    return False

            if not _sleep_until_next_poll(start_time, timeout, poll_interval):
                break

    elapsed = int(time.time() - start_time)
    console.print(f"\n[red]✗ Gateway timeout after {elapsed}s[/red]")
    return False
