# Fabric MVP Spike

This spike validates whether NeMo Agents can keep a Platform-owned agent
configuration while using the Fabric SDK for harness execution, runtime
lifecycle, result normalization, and Relay telemetry emission.

The main question tested here is:

> Can Platform translate an `agent.yaml`-style config into a typed
> `FabricConfig`, run supported harnesses through Fabric, and consume the
> resulting outputs/artifacts without making NeMo Agents depend on
> harness-specific execution logic?

## Files

- `agent.yaml`: Platform-owned prospective agent config.
- `script.py`: Spike runner that translates `agent.yaml` into `FabricConfig`
  and exercises Fabric plan, doctor, one-shot, runtime, and telemetry paths.
- `workspace/`: Local workspace used by Fabric harness invocations.
- `artifacts/`: Local output directory for Fabric run artifacts and Relay
  telemetry files.

## Setup

The spike expects:

- A bootstrapped `nemo-platform` virtualenv at `.venv`.
- A local NeMo-Fabric checkout at `~/workspace/NeMo-Fabric`, or
  `NEMO_FABRIC_REPO` pointing to that checkout.
- Codex CLI credentials if testing the `codex` harness.
- `NVIDIA_API_KEY` if testing the `hermes` harness.

Install the local Fabric SDK and adapters into the platform virtualenv:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py install-deps
```

This installs Fabric with the `codex`, `hermes`, `relay`, and `runtime` extras.

## Commands

Run a one-shot invocation through the default harness:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py run \
  --input "Say hello in one short sentence."
```

Run a one-shot invocation through Codex:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py run \
  --harness codex \
  --input "Say hello in one short sentence."
```

Run a one-shot invocation through Hermes:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py run \
  --harness hermes \
  --input "Say hello in one short sentence."
```

Run a multi-turn runtime:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py run-runtime \
  --harness hermes \
  --input "My project codename is Robin." \
  --second-input "What is my project codename?"
```

Enable Relay telemetry for a run:

```bash
python3 plugins/nemo-agents/examples/fabric-mvp-spike/script.py run \
  --harness hermes \
  --enable-relay-telemetry \
  --input "Say hello in one short sentence."
```

## Validated Flow

### Platform Config Translation

`agent.yaml` models a Platform-owned agent artifact rather than a Fabric-native
profile. The script resolves:

- default harness selection,
- per-harness model overrides,
- fallback default model configuration,
- harness-specific settings,
- local workspace/artifact directories,
- optional Relay telemetry configuration.

The script then translates the selected harness into a typed `FabricConfig`.
This keeps Fabric as the execution boundary while letting Platform own the user
facing config shape.

### Plan And Doctor

Before invocation, the script calls:

- `fabric.plan(...)`
- `fabric.doctor(...)`

The spike confirmed that this can validate the effective Fabric config and
preflight the selected harness before execution. The script only proceeds when
doctor reports an overall `pass` status.

### One-Shot Invocation

The script uses `fabric.run(...)` for ephemeral one-shot invocation.

Validated harnesses:

- `codex` via `nvidia.fabric.codex.cli`
- `hermes` via `nvidia.fabric.hermes.sdk`

For this path, Platform can treat the runtime as implementation detail:
Fabric starts the runtime, invokes the harness, captures outputs/artifacts, and
stops the runtime before returning `RunResult`.

### Multi-Turn Runtime

The script uses:

- `fabric.start_runtime(...)`
- `runtime.invoke(...)`
- `runtime.stop()`

The spike validated that a single runtime can handle multiple turns and preserve
state for session-oriented agents.

Observed behavior:

- Hermes exposes normalized message history through the runtime.
- Codex preserves continuity through its own thread/state handling.
- Both turns use the same Fabric runtime ID.
- The runtime reaches `stopped` after `runtime.stop()`.

### Relay Telemetry

Relay telemetry is disabled by default in `agent.yaml`, but the config includes
the intended output convention:

- `events.atof.jsonl`
- `trajectory-{session_id}.atif.json`
- output under `./artifacts/relay`

Passing `--enable-relay-telemetry` translates that Platform telemetry config into
`FabricConfig.enable_relay(...)`.

Validated results:

- Codex emitted ATOF telemetry as NDJSON.
- Hermes emitted both ATOF telemetry and ATIF trajectory JSON.
- `RunResult.artifacts` included telemetry artifacts with paths and media types.
- `RunResult.telemetry` included the Relay output directory, project, config
  path, and `relay_enabled: true`.

The generated Relay files are structured JSON/NDJSON artifacts. They include prompt, response, and model payload data, so they should
use the same protected logging path and access controls as other prompt-bearing
logs.

## Requirement Coverage

| Requirement | Spike result |
| --- | --- |
| Invoke an agent in a new ephemeral session | Covered with `fabric.run(...)`. |
| Invoke an existing session for session-oriented agents | Covered with `start_runtime(...)` and repeated `runtime.invoke(...)`. |
| Start a long-running agent runtime | Covered locally with `start_runtime(...)`; Platform still needs product/API shape. |
| Specify runtime configs such as hyperparams, system prompts, tools, and skills | Partially covered by translating model/settings/system prompt fields; tools and skills remain config-shape follow-up. |
| Support telemetry collection and emission with Relay routing | Covered for ATOF and ATIF artifacts. |
| Support input types beyond text prompts, such as files | Not validated in this spike. |
| Stop or cancel a long-running runtime/session | Stop covered with `runtime.stop()`; cancel was not validated. |

## Platform Implications

Fabric appears to provide the execution primitives needed by Platform:

- typed config boundary through `FabricConfig`,
- plan/preflight,
- one-shot execution,
- managed runtime execution,
- normalized run results,
- lifecycle stop,
- artifact reporting,
- Relay telemetry emission.

The remaining Platform work is mostly product and API shape:

- define the Platform-owned `agent.yaml` schema,
- translate that schema into `FabricConfig`,
- decide the CLI/API split between `invoke`, `run`, `deploy`, and `stop`,
- persist and expose runtime/deployment IDs,
- route Relay artifacts into the Platform log service,
- define the first supported non-text input shape.
