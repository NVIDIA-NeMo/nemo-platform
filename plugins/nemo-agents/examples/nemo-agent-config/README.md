# NeMo Agent Config

This directory contains example Platform-owned `agent.yaml` configs for
Fabric-backed NeMo Agents. Run the commands below from the repository root.

Fabric dependencies are currently optional so the default workspace does not
force other Fabric consumers onto the current Fabric SDK/runtime API before they
migrate.

```bash
uv pip install -e "plugins/nemo-agents[fabric]"
```

For Codex/Claude Relay telemetry, install the Relay CLI separately:

```bash
cargo install nemo-relay-cli --root .venv
.venv/bin/nemo-relay --version
```

Top-level `skills`, `mcp`, and `tools` are Platform-owned shared fields that
translate into `FabricConfig`. Prompt settings are harness-specific for now and
should be configured under `harnesses.<name>.settings`.

## Local invoke

`agent.yaml` is the telemetry-neutral example. Authenticate Codex, then run:

```bash
codex login

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent.yaml \
  --input "Reply with exactly: platform fabric works"
```

To try Claude, authenticate Claude Code first:

```bash
claude
```

Temporarily set `default_harness: claude` in `agent.yaml`, then run the same
`nemo agents invoke` command.

## Relay Local Files

`agent-relay.yaml` enables Relay telemetry without Intake. It writes local ATIF
and ATOF artifacts under the deployment artifacts directory.

```bash
nemo agents create \
  --name fabric-relay-local-test \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent-relay.yaml

nemo agents deploy \
  --agent fabric-relay-local-test \
  --name fabric-relay-local-test-deployment \
  --mode subprocess

nemo agents invoke \
  --agent-deployment fabric-relay-local-test-deployment \
  --input "Reply with exactly: relay local works"
```

Confirm Relay emitted both ATIF and ATOF files:

```bash
find ~/.local/share/nemo/agents/system/default/fabric-relay-local-test-deployment-fabric/artifacts \
  \( -name "*atif*" -o -name "*atof*" \) \
  -exec ls -lh {} \;
```

## Hermes

Hermes Agent has dependencies that conflict with the Platform environment, so
install it with the Fabric adapter in a separate Python 3.12 environment:

```bash
uvx uv@0.9.14 venv --python 3.12 .venv-hermes
uvx uv@0.9.14 --no-config pip install \
  --python .venv-hermes/bin/python \
  "nemo-fabric[relay]>=0.1.0rc4,<0.2.0" \
  "nemo-fabric-adapters-hermes>=0.1.0rc4,<0.2.0" \
  "hermes-agent==0.19.0"

export HERMES_ADAPTER_PYTHON="$PWD/.venv-hermes/bin/python"
export NVIDIA_API_KEY="<your NVIDIA API key>"
```

Temporarily set `default_harness: hermes` in `agent.yaml`, then run:

```bash
nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent.yaml \
  --input "Reply with exactly: platform hermes works"
```

## Relay to Intake (Local)

`agent-relay-intake.yaml` enables Relay ATIF export to a locally running
Platform Intake API. Start ClickHouse for Intake, start Platform, then create
and deploy the agent:

```bash
services/intake/scripts/spans/run_clickhouse.sh

nemo agents create \
  --name fabric-relay-intake \
  --agent-config plugins/nemo-agents/examples/nemo-agent-config/agent-relay-intake.yaml

nemo agents deploy \
  --agent fabric-relay-intake \
  --name fabric-relay-intake-deployment \
  --mode subprocess

nemo agents invoke \
  --agent-deployment fabric-relay-intake-deployment \
  --input "Reply with exactly: platform fabric works"
```

Confirm Intake received ATIF-derived spans:

```bash
curl -g -s "http://127.0.0.1:8080/apis/intake/v2/workspaces/default/spans?page_size=20" \
  | jq '.data[] | {session_id, name, source, started_at}'
```

To inspect traces in Studio, run the web app with Intake enabled:

```bash
cd web
VITEST=true \
VITE_FF_INTAKE_ENABLED=true \
VITE_PLATFORM_BASE_URL=http://localhost:8080 \
pnpm --filter nemo-studio-ui start --host 127.0.0.1
```

Then open `http://localhost:5173/studio/workspaces/default/intake/traces`.
