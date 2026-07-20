# nemo-rl-plugin

NeMo-RL customization contributor for the NeMo Platform. Adds **DPO** training
on a Ray cluster (via [NVIDIA NeMo-RL](https://github.com/NVIDIA-NeMo/RL)
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
- **DPO is full-weight** (no PEFT). GRPO/PPO are headroom (`TrainingMethod` is a
  single-member union today).

## Job spec

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

## Compiled job (4 steps)

`submit` → `RlJobInput` → transform → `RlJobOutput` → compiled `PlatformJobSpec`:

1. **download** — model fileset + preference dataset → PVC (CPU, `nmp-customizer-tasks`)
2. **dpo-training** — Ray DPO step (GPU, `nmp-rl-training`); single-node `gpu` or
   multi-node `gpu_distributed` executor, selected by `parallelism.num_nodes`
3. **upload** — trained checkpoint → output fileset (CPU)
4. **model-entity** — register the full-weight output `ModelEntity`

## Related

- **Skill:** the `nemo-customizer` skill documents the end-to-end DPO workflow
  (`plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/`).
- **Design:** [`docs/customizer/nemo-rl-dpo-plugin-design.md`](../../docs/customizer/nemo-rl-dpo-plugin-design.md).
- **GPU e2e smoke test:** [`scripts/gpu-dpo-smoke/`](../../scripts/gpu-dpo-smoke).
- **Images:** [`docker/Dockerfile.nmp-rl-base`](../../docker/Dockerfile.nmp-rl-base),
  `Dockerfile.nmp-rl-training`, `Dockerfile.nmp-customizer-tasks`.
