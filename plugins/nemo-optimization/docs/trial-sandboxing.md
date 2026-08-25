# Design note: sandboxing Optuna trials

Status: **proposed**, not implemented. Phase 4 of the fileset/executor work — it
does not block `nemo agents optimize submit`.

## The gap

Making `submit` remote-safe fixed *where the study's inputs come from*. It did
not change *how much the study trusts the Agent under Test*.

`OptimizeJob` isolation stops at the job process. The subprocess executor runs
that process directly on the jobs host; the cpu executor runs it in a task
container. Inside either one,
[`FabricTrialEvaluator.evaluate`](../src/nemo_optimization/backends/optuna/fabric_trial.py)
constructs a `FabricAgentRuntime` per trial repetition, which executes the
agent's harness **in that same process tree**. For a study of `n_trials ×
reps_per_param_set`, that is the AuT running with the job's full ambient
authority, dozens of times.

The AuT is author-supplied. It can write anywhere the job user can write, open
sockets, and — via `eval.run_hook` — import arbitrary Python and spawn MCP
servers. On the subprocess backend that ambient authority is *the platform
host*. Optimizing an untrusted agent package is not safe there today.

## Proposal

Swap the runtime `FabricTrialEvaluator` builds, behind an opt-in flag.

The evaluator-SDK already has the seam:
[`FabricContainerRuntime`](../../../packages/nemo_evaluator_sdk/src/nemo_evaluator_sdk/agent_eval/runtimes/fabric/container_runtime.py)
is an `AgentTaskRunner` with the same contract as `FabricAgentRuntime`, but runs
each Fabric task inside a sandbox obtained from a `SandboxProvider` —
`DockerSandboxProvider` being the one that exists. See
[`examples/fabric_container/run_e2e.py`](../../../packages/nemo_evaluator_sdk/examples/fabric_container/run_e2e.py)
for the wiring.

1. Add `runtime.sandbox: disabled | docker` to the optimize config (default
   `disabled` for local `run`; `docker` recommended for `submit`).
2. In `FabricTrialEvaluator.__init__`, branch on it: `FabricAgentRuntime` when
   disabled, `FabricContainerRuntime(provider=DockerSandboxProvider(...),
   secrets=...)` when enabled. `evaluate` is otherwise unchanged — both satisfy
   `AgentTaskRunner`.
3. Resolve the AuT's credential env vars through `secrets` rather than
   inheriting the job's environment, so the sandbox does not receive every
   secret the job happens to hold.

## Why this seam and not the others

| Layer | Mechanism | Verdict for Optuna |
|-------|-----------|--------------------|
| Per-trial Fabric container | `FabricContainerRuntime` + `DockerSandboxProvider` | **Proposed.** Same runner contract, already exercised by agent-eval, per-trial granularity matches the study loop |
| OpenShell Landlock / nftables policy | Deployments plugin policy | Later, and only if the AuT is packaged as a deployment-like runtime. Stronger egress control than Docker alone |
| GRPO OpenSandbox + `sandboxed_gym` | Job-level Gym host + episode broker | Not a fit. Built for untrusted Gym environments in RL; heavier than a per-trial Fabric eval and a different execution model |

## Constraints to resolve before implementing

- **Nested containers.** The subprocess backend needs the Docker socket on the
  jobs host. The cpu backend needs Docker-in-Docker, sibling containers, or a
  `SandboxProvider` that does not need a local daemon at all — nested Docker on
  plain Kubernetes Jobs is the hard part, and the reason this is not simply "turn
  it on for `submit`".
- **Egress is not default-deny.** `DockerSandboxProvider` gives process and
  filesystem isolation, not network isolation. A trial can still reach anything
  the job can reach. Production egress control needs OpenShell-style policy or
  nftables rules layered on top.
- **Cost.** A container per trial repetition, on top of a study that already
  multiplies trials by reps. Worth measuring against the subprocess path before
  making it the `submit` default.

Longer term, a `SandboxProvider` backed by OpenSandbox would give Kubernetes
optimize workers Kata/crun isolation without DinD, and would close the cpu-backend
gap above.
