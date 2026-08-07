# sandboxed-gym

Trusted **episode broker** + **job-level Gym host** orchestrator for running NeMo-Gym
inside an OpenSandbox (or compatible) isolation boundary.

This package has **no NeMo-RL / GRPO dependency**. Callers get raw Gym host
`/health` and `/rollouts/run` results. RL-specific postprocessing belongs in the
training client (e.g. NeMo-RL's thin `SandboxedGymActor` adapter).

## Install

```bash
pip install -e packages/sandboxed_gym
# optional Ray wrappers
pip install -e "packages/sandboxed_gym[ray]"
```

## Serve (always starts the episode broker)

```bash
# Mode A — local orchestrator proxy (recommended for cross-job clients)
sandboxed-gym serve --config serve.yaml --mode orchestrator --bind 0.0.0.0:8090 \
  --session-file /tmp/session.json

# Mode B — print Gym host URLs and wait
sandboxed-gym serve --config serve.yaml --mode host-urls --session-file /tmp/session.json
```

### Cross-job pattern

1. **Job A** runs `sandboxed-gym serve --mode orchestrator` with environment/dataset
   PVC mounts (same `SandboxConfig` shape as sandboxed GRPO).
2. Job A writes a `SandboxedGymSessionDescriptor` (`--session-file`).
3. **Job B** POSTs to Job A's orchestrator Service: `POST /rollouts/run`.

Set `episode_broker.advertise_url` to a stable Service DNS name so the Gym host
egress allowlist does not depend on a pod IP.

## Library

```python
from sandboxed_gym import SandboxedGymOrchestrator, SandboxedGymServeConfig

session = SandboxedGymOrchestrator().start(SandboxedGymServeConfig.model_validate(...))
results = session.run_rollouts([{"agent_ref": {...}, ...}])
session.shutdown()
```

## Config sketch

See `examples/serve.yaml`. Key fields:

- `sandbox.environment_pvc_claim` / `dataset_pvc_claim` / `workspace_pvc_claim`
- `episode_broker` (allowlists, TTL, `advertise_url`)
- `gym_global_config` — opaque Gym JSON injected as `NMP_GYM_GLOBAL_CONFIG`
- `rollout_auth_token` — optional bearer for the orchestrator proxy
