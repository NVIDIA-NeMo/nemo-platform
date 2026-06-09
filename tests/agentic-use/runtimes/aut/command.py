# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build the container command for the AUT backend."""

from __future__ import annotations

import textwrap

from runtimes.shared.constants import NAT_TRACE_EXPORT_SCRIPT_CONTAINER_PATH


def build_aut_agent_cmd(instruction_container: str) -> list[str]:
    """Build the ``bash -c`` command that drives the AUT (deep-agent) backend."""
    return [
        "bash",
        "-c",
        textwrap.dedent(f"""\
            set -euo pipefail
            EFFECTIVE_AUT_AGENT_CONFIG="${{AUT_AGENT_CONFIG}}"
            if [ -n "${{AUT_AGENT_CONFIG}}" ] && [ -n "${{NVIDIA_API_KEY:-}}" -o -n "${{ANTHROPIC_API_KEY:-}}" ]; then
              /app/.venv/bin/python -c "from pathlib import Path; import os; text = Path(os.environ['AUT_AGENT_CONFIG']).read_text(); text = text.replace('\\${{NVIDIA_API_KEY}}', os.environ.get('NVIDIA_API_KEY', '')); text = text.replace('\\${{ANTHROPIC_API_KEY}}', os.environ.get('ANTHROPIC_API_KEY', '')); Path('/tmp/aut_agent.resolved.yml').write_text(text)"
              EFFECTIVE_AUT_AGENT_CONFIG="/tmp/aut_agent.resolved.yml"
            fi
            if /app/.venv/bin/nemo agents get "${{AUT_AGENT_NAME}}" >/tmp/aut_get_before.log 2>&1; then
              if [ -n "${{EFFECTIVE_AUT_AGENT_CONFIG}}" ]; then
                echo "AUT '${{AUT_AGENT_NAME}}' already exists; recreating from AUT_AGENT_CONFIG."
                /app/.venv/bin/nemo agents undeploy --agent "${{AUT_AGENT_NAME}}" >/tmp/aut_undeploy_before_recreate.log 2>&1 || true
                /app/.venv/bin/nemo agents delete "${{AUT_AGENT_NAME}}" >/tmp/aut_delete_before_recreate.log 2>&1 || true
                /app/.venv/bin/nemo agents create --name "${{AUT_AGENT_NAME}}" --agent-config "${{EFFECTIVE_AUT_AGENT_CONFIG}}" >/tmp/aut_create.log 2>&1
              else
                echo "AUT '${{AUT_AGENT_NAME}}' already exists."
              fi
            else
              if [ -z "${{EFFECTIVE_AUT_AGENT_CONFIG}}" ]; then
                echo "AUT agent '${{AUT_AGENT_NAME}}' not found and no AUT_AGENT_CONFIG was provided." >&2
                echo "Set --aut-agent-config or AUT_AGENT_CONFIG so the runner can create the agent." >&2
                echo "Expected resolved config path in container env: '${{AUT_AGENT_CONFIG:-<unset>}}'" >&2
                cp /tmp/aut_get_before.log /logs/agent/aut_get_before.log 2>/dev/null || true
                exit 1
              fi
              /app/.venv/bin/nemo agents create --name "${{AUT_AGENT_NAME}}" --agent-config "${{EFFECTIVE_AUT_AGENT_CONFIG}}" >/tmp/aut_create.log 2>&1
            fi
            if [ "${{AUT_SEED_PROVIDERS:-1}}" = "1" ]; then
              /app/.venv/bin/python /app/tests/agentic-use/seed_providers.py \
                --manifest /app/tests/agentic-use/providers.yaml \
                --base-url "${{NMP_BASE_URL:-http://localhost:8080}}" \
                2>&1 | tee /tmp/aut_provider_seed.log
            fi
            collect_aut_diagnostics() {{
              local restore_errexit=0
              case "$-" in
                *e*) restore_errexit=1 ;;
              esac
              set +e
              /app/.venv/bin/nemo agents deployments list >/tmp/aut_deployments.list.json 2>&1
              cp /tmp/aut_deployments.list.json /logs/agent/aut_deployments.list.json 2>/dev/null || true
              dep_name=$(
                /app/.venv/bin/python -c "import json,sys; data=json.load(sys.stdin).get('data', []); match=next((d.get('name') for d in data if d.get('agent') == '${{AUT_AGENT_NAME}}'), ''); print(match)" </tmp/aut_deployments.list.json 2>/dev/null
              )
              if [ -n "$dep_name" ]; then
                /app/.venv/bin/nemo agents deployments get "$dep_name" >/tmp/aut_deployment.get.json 2>&1
                cp /tmp/aut_deployment.get.json /logs/agent/aut_deployment.get.json 2>/dev/null || true
              fi
              cp /tmp/aut_create.log /logs/agent/aut_create.log 2>/dev/null || true
              cp /tmp/aut_get_before.log /logs/agent/aut_get_before.log 2>/dev/null || true
              cp /tmp/aut_provider_seed.log /logs/agent/aut_provider_seed.log 2>/dev/null || true
              cp /tmp/aut_undeploy.log /logs/agent/aut_undeploy.log 2>/dev/null || true
              cp /tmp/aut_undeploy_before_recreate.log /logs/agent/aut_undeploy_before_recreate.log 2>/dev/null || true
              cp /tmp/aut_delete_before_recreate.log /logs/agent/aut_delete_before_recreate.log 2>/dev/null || true
              cp /tmp/nmp-api.log /logs/agent/nmp-api.log 2>/dev/null || true
              mkdir -p /logs/agent/nat_subprocess_logs 2>/dev/null || true
              if [ -d /logs/agent/nat_subprocess_logs ]; then
                ( /app/.venv/bin/nemo agents logs --agent "${{AUT_AGENT_NAME}}" --path 2>/dev/null | while read -r aut_log_path; do
                  if [ -n "$aut_log_path" ] && [ -f "$aut_log_path" ]; then
                    cp "$aut_log_path" /logs/agent/nat_subprocess_logs/ 2>/dev/null || true
                  fi
                done ) || true
              fi
              if [ "$restore_errexit" -eq 1 ]; then
                set -e
              fi
              return 0
            }}
            cleanup() {{
              cleanup_rc=$?
              set +e
              collect_aut_diagnostics
              /app/.venv/bin/nemo agents undeploy --agent "${{AUT_AGENT_NAME}}" >/tmp/aut_undeploy_after.log 2>&1 || true
              cp /tmp/aut_undeploy_after.log /logs/agent/aut_undeploy_after.log 2>/dev/null || true
              cp /tmp/nat_agent.log /logs/agent/nat_agent.log 2>/dev/null || true
              exit "$cleanup_rc"
            }}
            trap cleanup EXIT
            /app/.venv/bin/nemo agents undeploy --agent "${{AUT_AGENT_NAME}}" >/tmp/aut_undeploy.log 2>&1 || true
            /app/.venv/bin/nemo agents deploy --agent "${{AUT_AGENT_NAME}}"
            /app/.venv/bin/nemo agents deployments wait --agent "${{AUT_AGENT_NAME}}"
            dep_endpoint=$(
              /app/.venv/bin/nemo agents deployments list 2>/dev/null | /app/.venv/bin/python -c "import json,sys; data=json.load(sys.stdin).get('data', []); match=next((d.get('endpoint') for d in data if d.get('agent') == '${{AUT_AGENT_NAME}}' and d.get('status') == 'running' and d.get('endpoint')), ''); print(match)"
            )
            if [ -z "$dep_endpoint" ]; then
              echo "No running AUT deployment endpoint found for agent '${{AUT_AGENT_NAME}}'." >&2
              exit 1
            fi
            health_wait="${{AUT_HEALTH_WAIT_SECONDS:-60}}"
            aut_healthy=0
            for i in $(seq 1 "$health_wait"); do
              if curl -sf "$dep_endpoint/health" >/dev/null 2>&1; then
                aut_healthy=1
                break
              fi
              sleep 1
            done
            if [ "$aut_healthy" -ne 1 ]; then
              echo "AUT deployment did not become healthy within $health_wait seconds: $dep_endpoint" >&2
              exit 1
            fi
            set +e
            /app/.venv/bin/python {NAT_TRACE_EXPORT_SCRIPT_CONTAINER_PATH} invoke-aut \
              --endpoint "$dep_endpoint" \
              --instruction {instruction_container} \
              --output-dir /logs/agent \
              --timeout "${{AUT_INVOKE_HTTP_TIMEOUT:-600}}" \
              2>&1 | tee /tmp/nat_agent.log
            rc=${{PIPESTATUS[0]}}
            set -e
            if [ $rc -ne 0 ]; then
              collect_aut_diagnostics
            fi
            exit $rc
        """),
    ]
