# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the container command for the NAT workflow backend."""

from __future__ import annotations

import textwrap

from runtimes.shared.constants import NAT_TRACE_EXPORT_SCRIPT_CONTAINER_PATH


def build_workflow_agent_cmd(workflow_container: str, instruction_container: str) -> list[str]:
    """Build the ``bash -c`` command that runs the ``nat run`` workflow backend."""
    return [
        "bash",
        "-c",
        textwrap.dedent(f"""\
            /app/.venv/bin/nat run \\
              --config_file {workflow_container} \\
              --input "$(cat {instruction_container})" \\
              2>&1 | tee /tmp/nat_agent.log
            EXIT=${{PIPESTATUS[0]}}
            cp /tmp/nat_agent.log /logs/agent/nat_agent.log 2>/dev/null || true
            if [ -f /logs/agent/intermediate_steps.jsonl ]; then
              /app/.venv/bin/python {NAT_TRACE_EXPORT_SCRIPT_CONTAINER_PATH} convert-jsonl \\
                --input /logs/agent/intermediate_steps.jsonl \\
                --output /logs/agent/trajectory.json \\
                >> /tmp/nat_agent.log 2>&1
              CONVERT_EXIT=$?
              cp /tmp/nat_agent.log /logs/agent/nat_agent.log 2>/dev/null || true
              if [ $EXIT -eq 0 ] && [ $CONVERT_EXIT -ne 0 ]; then
                exit $CONVERT_EXIT
              fi
            elif [ $EXIT -eq 0 ]; then
              echo "NAT telemetry exporter did not create /logs/agent/intermediate_steps.jsonl" | tee -a /tmp/nat_agent.log
              cp /tmp/nat_agent.log /logs/agent/nat_agent.log 2>/dev/null || true
              exit 1
            fi
            exit $EXIT
        """),
    ]
