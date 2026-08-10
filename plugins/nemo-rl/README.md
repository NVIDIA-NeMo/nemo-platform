# nemo-rl-plugin

NeMo-RL customization contributor for the NeMo Platform. Adds **DPO** and **GRPO**
training on a Ray cluster (via [NVIDIA NeMo-RL](https://github.com/NVIDIA-NeMo/RL)
v0.6.0) as the `rl` backend under `/apis/customization`.

Thin contributor layer only — the heavy compile glue and container tasks live in
[`services/rl`](../../services/rl) (`nmp-rl`).

## Surfaces

- **CLI:** `nemo customization rl submit <job.json> -w <workspace>` (submit-only;
  `run` is disabled — there is no local execution).
- **REST:** `POST /apis/customization/v2/workspaces/{workspace}/rl/jobs`
- **SDK:** `client.customization.rl.jobs.create(...)`

## Constraints

- **Remote Kubernetes only** — gated via `require_distributed_runtime`. There is
  no local Docker fallback (unlike automodel/unsloth).
- **Single-node multi-GPU and multi-node** both supported (`parallelism.num_nodes`).
  Multi-node requires `NMP_RL_MULTINODE_SHARED_STORAGE_PATH`.
- **DPO is full-weight** (no PEFT). **GRPO** uses NeMo Gym environments (Prime
  Intellect hub envs packaged as `adapter-wheels-v1` FileSets).
- **GRPO sandboxed mode** defaults from platform config (`sandboxed_gym_default=true`).
  Compile fails closed when OpenSandbox is unavailable (set
  `NMP_RL_SANDBOX_CLUSTER_CAPABLE=true` once installed) or when
  `NMP_RL_JOB_STORAGE_PVC_CLAIM` is unset — the Gym sandbox re-mounts that claim to
  read the downloaded environment and dataset. Set `NMP_RL_SANDBOXED_GYM_DEFAULT=false`
  for trusted dev smoke tests only.
- **`training.type` is required** in submitted JSON (union discriminator); it does not
  default to `dpo`.

## Job spec

### DPO

`model` and `dataset` are string refs; the method lives under `training` with
`type: "dpo"`. The `dataset` fileset holds **both** `training.jsonl` and
`validation.jsonl` as `{prompt, chosen, rejected}` preference rows.

```json
{
  "model": "default/qwen3-0.6b",
  "dataset": "default/dpo-data",
  "training": {
    "type": "dpo",
    "epochs": 1,
    "learning_rate": 5e-6,
    "max_seq_length": 1024,
    "batch_size": 32,
    "micro_batch_size": 1,
    "ref_policy_kl_penalty": 0.05,
    "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1 }
  },
  "output": { "name": "qwen3-0.6b-dpo" }
}
```

Configurable `training` knobs (full reference: the skill's
`references/hyperparameters.md` § NeMo-RL (DPO)): the optimizer/schedule/batch
fields, `parallelism`, `optimizer_type`, `adam_eps`, `activation_checkpointing`,
`keep_top_k`, `val_at_end`, and the DPO-specific `ref_policy_kl_penalty`,
`preference_loss_weight`, `sft_loss_weight`, `preference_average_log_probs`,
`sft_average_log_probs`, `max_grad_norm`. `RlJobInput` (`schema.py`) is the
authoritative input shape; `nemo customization rl explain` prints it live.

### GRPO (NeMo Gym)

1. **Convert** a Prime Intellect hub environment on an internet-capable host (no cluster egress):

   ```bash
   pi-to-gym-conversion --hub-id primeintellect/ascii-tree --out-dir ./ascii-tree-pkg
   ```

   Emits an `adapter-wheels-v1` tree + Gym JSONL dataset. Upload both as FileSets
   (`purpose=environment` and `purpose=dataset`).

2. **Submit** GRPO with `environment` + Gym JSONL `dataset`:

   ```json
   {
     "model": "default/qwen3-0.6b",
     "dataset": "default/ascii-tree-gym-data",
     "environment": "default/ascii-tree-env",
     "training": {
       "type": "grpo",
       "epochs": 1,
       "batch_size": 32,
       "micro_batch_size": 1,
       "num_generations_per_prompt": 8,
       "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1 }
     },
     "output": { "name": "qwen3-0.6b-grpo" }
   }
   ```

   The compiler downloads model + dataset + environment, emits path-only NeMo-RL
   YAML with `env.nemo_gym.sandboxed` from platform config (default `true`), and
   injects vLLM/broker egress env vars for sandboxed rollouts.

## Compiled job (4 steps)

`submit` → `RlJobInput` → transform → `RlJobOutput` → compiled `PlatformJobSpec`:

1. **download** — model fileset + dataset (+ environment for GRPO) → PVC (CPU, `nmp-customizer-tasks`)
2. **dpo-training** / **grpo-training** — Ray step (GPU, `nmp-rl-training`); single-node `gpu` or
   multi-node `gpu_distributed` executor, selected by `parallelism.num_nodes`
3. **upload** — trained checkpoint → output fileset (CPU)
4. **model-entity** — register the full-weight output `ModelEntity`

## Related

- **Skill:** the `nemo-customizer` skill documents the end-to-end DPO workflow
  (`plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/`).
- **Design:** [`docs/customizer/nemo-rl-dpo-plugin-design.md`](../../docs/customizer/nemo-rl-dpo-plugin-design.md).
- **GPU e2e smoke test:** [`scripts/gpu-dpo-smoke/`](../../scripts/gpu-dpo-smoke).
- **Images:** [`docker/rl/Dockerfile.nmp-rl-base`](../../docker/rl/Dockerfile.nmp-rl-base),
  [`docker/rl/Dockerfile.nmp-rl-training`](../../docker/rl/Dockerfile.nmp-rl-training),
  `docker/Dockerfile.nmp-customizer-tasks`.
