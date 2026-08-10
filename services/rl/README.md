# nmp-rl

NeMo-RL task package for the NeMo Platform Customizer. Provides the compile glue
and the container-side tasks for **DPO** and **GRPO** (NeMo Gym) run on a Ray
cluster via [NVIDIA NeMo-RL](https://github.com/NVIDIA-NeMo/RL). The training
image bases on the published NGC container `nvcr.io/nvidia/nemo-rl:v0.6.0`
(amd64 + arm64, Python 3.13).

No HTTP server. The thin contributor layer lives in
[`plugins/nemo-rl`](../../plugins/nemo-rl); this package holds:

- `nmp.rl.schemas` — canonical `RlJobOutput` / `DPOTraining` / `GRPOTraining`.
- `nmp.rl.schemas.environment` — `adapter-wheels-v1` manifest + Gym JSONL row types.
- `nmp.rl.compile` / `nmp.rl.app.jobs.compiler` — the 4-step `PlatformJobSpec`
  (download → DPO/GRPO train → upload → model-entity). The training step's executor
  is chosen by `parallelism.num_nodes` (single-node `gpu` vs multi-node
  `gpu_distributed`).
- `nmp.rl.tasks.environment` — CLI convert (`pi-to-gym-conversion`) for
  Prime Intellect hub → `adapter-wheels-v1` + Gym JSONL (internet-capable host).
- `nmp.rl.tasks.training` — GPU training entrypoint (bootstraps Ray and runs the
  DPO or GRPO driver). CPU `file_io` / `model_entity` steps run from the shared
  `nmp-customizer-tasks` image (`nmp.customization_common.tasks.*`).

## Scope

- **Remote Kubernetes only.** There is no local Docker fallback; `compile()`
  requires `platform.runtime: kubernetes` (via
  `require_distributed_runtime`).
- **Single-node multi-GPU and multi-node** are both supported. Multi-node
  (`num_nodes > 1`) additionally requires a shared filesystem
  (`NMP_RL_MULTINODE_SHARED_STORAGE_PATH`) for Ray's cross-node coordination;
  `compile()` fails fast otherwise.
- **DPO and GRPO are full-weight only** (PEFT unsupported). GRPO uses NeMo Gym
  environment FileSets; `sandboxed` comes from platform config
  (`NMP_RL_SANDBOXED_GYM_DEFAULT`, default `true`), and sandboxed jobs additionally
  require `NMP_RL_SANDBOX_CLUSTER_CAPABLE=true` and `NMP_RL_JOB_STORAGE_PVC_CLAIM`.
- **Do not edit checked-in OpenAPI YAML** as part of RL schema work; Pydantic is
  the source of truth until a separate OpenAPI regen pass.
