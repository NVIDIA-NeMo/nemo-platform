# Sandbox seam (AALGO-321)

A provider-neutral sandbox contract for running agent-eval harnesses **inside a container**,
injecting context and retrieving artifacts across the boundary. Built for
[`FabricContainerRuntime`](../fabric/container_runtime.py) but usable by any runtime.

## Why an owned seam (not `nemo_gym.sandbox` directly)

`nemo_gym.sandbox` ships the same *shape* (exec + programmatic file I/O + async/sync facades), and
this seam deliberately mirrors it so a Gym backend could be adapted later. We do **not** depend on
the package because: it requires Python ≥3.12 (nemo-platform is 3.11) and pulls `ray`/`wandb`/`mlflow`;
importing it monkeypatches builtin `print` and mutates `sys.path`/HF env; and neither shipped Gym
backend (Apptainer, OpenSandbox) matches nemo-platform's Docker-local / Kubernetes-scale target — so
we write the providers ourselves regardless. See AALGO-321 for the full analysis.

## The contract

- [`base.py`](base.py) — `SandboxSpec`, `SandboxResources`, `SandboxExecResult`, `SandboxHandle`,
  and the `SandboxProvider` Protocol. File transfer is programmatic (`upload_*`/`download_*`), not
  mount-based, so it crosses a **remote** API boundary (`docker cp` today → `kubectl cp` next), which
  bind mounts cannot.
- [`api.py`](api.py) — `AsyncSandbox` (what runtimes use) and a thin sync `Sandbox`. Drives
  `create → seed files → exec → transfer → close`; tears a half-created sandbox down on seed failure.
- [`providers/docker.py`](providers/docker.py) — `DockerSandboxProvider`: one persistent container
  per sandbox (`docker run -d` keep-alive), `docker exec`, `docker cp`, `docker rm -f`. Single `_run`
  chokepoint (mocked in unit tests).

## Isolation note

The Docker provider does **not** default to `--network none`: the agent harness needs egress to reach
its model endpoint. `network` is a provider option. Endpoint-scoped egress control (allow the model
API, deny the rest) is future work for a policy-capable backend (e.g. NVIDIA OpenShell), not this
provider.

## Roadmap

Docker (local, here) → agent-sandbox / k8s-sigs (remote scale; `Sandbox` CRD + Python SDK) →
NVIDIA OpenShell (once it exposes a programmatic file-I/O API; CLI/SSH-only today).

## Tests

- `tests/agent_eval/test_sandbox_docker_provider.py` — hermetic; asserts the exact `docker` argv.
- `tests/agent_eval/test_sandbox_api.py` — facade lifecycle over a fake provider.
- `tests/agent_eval/test_sandbox_docker_provider_live.py` — real `docker`; skipped without a daemon.
- `tests/agent_eval/test_fabric_container_runtime.py` — evidence-contract mapping over a fake provider.
