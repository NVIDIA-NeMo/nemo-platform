# nmp-rl

NeMo-RL task package for the NeMo Platform Customizer. Provides the compile glue
and the container-side tasks for **Direct Preference Optimization (DPO)** run on
a Ray cluster via [NVIDIA NeMo-RL](https://github.com/NVIDIA-NeMo/RL). The
training image bases on the published NGC container
`nvcr.io/nvidia/nemo-rl:v0.6.0` (amd64 + arm64, Python 3.13).

No HTTP server. The thin contributor layer lives in
[`plugins/nemo-rl`](../../plugins/nemo-rl); this package holds:

- `nmp.rl.schemas` — canonical `RlJobOutput` / `DPOTraining`.
- `nmp.rl.compile` / `nmp.rl.app.jobs.compiler` — the 4-step `PlatformJobSpec`
  (download → DPO train → upload → model-entity). The training step's executor
  is chosen by `parallelism.num_nodes` (single-node `gpu` vs multi-node
  `gpu_distributed`).
- `nmp.rl.tasks.*` — container entrypoints (`file_io`, `model_entity`,
  `training`). The training task bootstraps a Ray cluster and runs the DPO
  driver against the NeMo-RL library.

## Scope

- **Remote Kubernetes only.** There is no local Docker fallback; `compile()`
  requires `platform.runtime: kubernetes` (via
  `require_distributed_runtime`).
- **Single-node multi-GPU and multi-node** are both supported. Multi-node
  (`num_nodes > 1`) additionally requires a shared filesystem
  (`NMP_RL_MULTINODE_SHARED_STORAGE_PATH`) for Ray's cross-node coordination;
  `compile()` fails fast otherwise.
- **DPO is full-weight only** (PEFT unsupported). GRPO/PPO are reserved as
  headroom in the schema/driver layout.
