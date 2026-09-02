# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Submit an Insights Analyst demo run through the Insights analysis-runs API.

This script is intentionally REST-shaped so the demo is easy to show with curl
or a local platform server. The Insights API translates this request into the
generic ``agents.execute`` job. The route
composes the Analyst config from the supplied model pair and submits it as an
inline agent definition, so there is no Analyst Agent entity to provision.

With ``--wait`` it polls the backing job to a terminal state and prints the
``analysis-report`` result the ``insights.analysis`` execute extension saved —
the durable comparison point against the existing ``AnalyzeJob``.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

import httpx

TERMINAL_STATUSES = {"completed", "error", "cancelled"}
REPORT_RESULT_NAME = "analysis-report"


def main() -> None:
    args = _parse_args()
    payload: dict[str, Any] = {
        "agent": args.target_agent,
        "default_model": args.default_model,
        "fast_model": args.fast_model,
        "timeout_seconds": args.timeout_seconds,
    }
    base_url = args.base_url.rstrip("/")
    url = f"{base_url}/apis/insights/v2/workspaces/{args.workspace}/analysis-runs"
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return

    with httpx.Client(timeout=args.request_timeout) as client:
        response = client.post(url, json=payload)
        if response.status_code >= 400:
            raise SystemExit(f"Failed to create analysis run ({response.status_code}): {response.text}")
        job = response.json()["job"]
        job_name = job["name"]
        print(f"Created execute-agent job '{job_name}' (status: {job.get('status')}).")
        if not args.wait:
            print(f"Poll it with: GET {base_url}/apis/agents/v2/workspaces/{args.workspace}/jobs/execute/{job_name}")
            return
        status = _wait_for_terminal(client, base_url, args.workspace, job_name, args.poll_timeout, args.poll_interval)
        print(f"Job '{job_name}' finished with status '{status}'.")
        _print_report(client, base_url, args.workspace, job_name)
        if status != "completed":
            raise SystemExit(1)


def _wait_for_terminal(
    client: httpx.Client,
    base_url: str,
    workspace: str,
    job_name: str,
    poll_timeout: float,
    poll_interval: float,
) -> str:
    job_url = f"{base_url}/apis/agents/v2/workspaces/{workspace}/jobs/execute/{job_name}"
    deadline = time.monotonic() + poll_timeout
    last_status = ""
    while time.monotonic() < deadline:
        response = client.get(job_url)
        response.raise_for_status()
        status = str(response.json().get("status") or "")
        if status != last_status:
            print(f"  status: {status}")
            last_status = status
        if status in TERMINAL_STATUSES:
            return status
        time.sleep(poll_interval)
    raise SystemExit(f"Timed out after {poll_timeout}s waiting for job '{job_name}' (last status: {last_status!r}).")


def _print_report(client: httpx.Client, base_url: str, workspace: str, job_name: str) -> None:
    """Print the saved analysis report, or explain why it is absent."""
    results_url = f"{base_url}/apis/agents/v2/workspaces/{workspace}/jobs/execute/{job_name}/results"
    response = client.get(results_url)
    response.raise_for_status()
    names = [result["name"] for result in response.json()["data"]]
    if REPORT_RESULT_NAME not in names:
        print(f"No '{REPORT_RESULT_NAME}' result was saved. Available results: {', '.join(names) or '(none)'}")
        return

    download = client.get(f"{results_url}/{REPORT_RESULT_NAME}/download", follow_redirects=True)
    download.raise_for_status()
    print(f"\n--- {REPORT_RESULT_NAME} ---")
    print(download.text)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--workspace", default="default")
    parser.add_argument("--target-agent", default="demo-agent")
    parser.add_argument(
        "--default-model", required=True, help="Model Entity ref, e.g. default/nvidia-nemotron-3-super-120b-a12b."
    )
    parser.add_argument(
        "--fast-model", required=True, help="Model Entity ref, e.g. default/nvidia-nemotron-3-nano-30b-a3b."
    )
    parser.add_argument("--timeout-seconds", type=float, default=3600.0, help="Execute-job Fabric timeout.")
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--wait", action="store_true", help="Poll the job and print its analysis report.")
    parser.add_argument("--poll-timeout", type=float, default=900.0)
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
