<!-- NeMo-RL (DPO) job JSON reference. Index + source-of-truth: `hyperparameters.md`. Preference dataset formats: `dataset-formats.md` § NeMo-RL. -->

# NeMo-RL (DPO) job JSON

The `rl` backend (`nemo customization rl submit`) runs **DPO** (Direct Preference Optimization) on a Ray cluster — **Kubernetes runtime only**, full-weight (no LoRA). Schema: `RlJobInput` in `plugins/nemo-rl/src/nemo_rl_plugin/schema.py`. Run `nemo customization rl explain` for the live schema.

## Job JSON layout

```json
{
  "model": "default/<model-entity>",
  "dataset": "default/<preference-fileset>",
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
  "output": { "name": "<output-name>" }
}
```

- `model` is a **string** ref to a registered model entity (`"name"` or `"workspace/name"`) — not an object (unsloth) and not the HF id.
- `dataset` is a **single string** ref to a preference fileset containing `training.jsonl` + `validation.jsonl` (see `references/dataset-formats.md` § NeMo-RL). There is no separate validation ref.
- `output.name` is the full-weight model entity the job registers. DPO output type is always `model` (no adapter).

## Field reference — `training` (DPOTraining)

### General (shared training knobs)

| Field | Default | Notes |
|-------|---------|-------|
| `learning_rate` | `1e-4` | Peak LR. DPO typically uses a **low** LR (e.g. `5e-6`–`1e-5`). |
| `min_learning_rate` | `null` | Floor for cosine decay. |
| `weight_decay` | `0.01` | |
| `adam_beta1` / `adam_beta2` | `0.9` / `0.999` | Adam betas. |
| `adam_eps` | `1e-5` | Adam epsilon (numerical stability). |
| `warmup_steps` | `0` | Linear warmup steps. |
| `optimizer_type` | `null` → `adamw_with_cosine_annealing` | One of `adamw_with_cosine_annealing`, `adam_with_cosine_annealing`, `adamw_with_flat_lr`, `adam_with_flat_lr` (optimizer × LR-scheduler). |
| `epochs` | `1` | Passes over the dataset. |
| `max_steps` | `null` | Global step cap. Caps the run at `min(max_steps, epochs × steps_per_epoch)`, so it's safe to combine with `epochs` to stop smoke jobs mid-epoch — omit for real runs. |
| `val_check_interval` | `null` | Float ≤ 1.0 = fraction of epoch; > 1.0 = step count. |
| `val_at_end` | `true` | Run a final validation pass after the last step. Keep enabled: it makes the final checkpoint carry validation metrics so best-checkpoint selection (`metric_name`/`keep_top_k`) works — otherwise NeMo-RL warns and falls back to the latest checkpoint. Set `false` only to skip the extra eval. |
| `keep_top_k` | `1` | Number of best checkpoints to retain (ranked by validation loss). |
| `batch_size` | `32` | Global batch (preference **pairs**) across all GPUs. |
| `micro_batch_size` | `1` | Per-GPU micro batch. |
| `max_seq_length` | `2048` | Max token sequence length. |
| `activation_checkpointing` | `false` | Recompute activations in the backward pass to cut memory — the first knob to enable for OOM / larger models / longer sequences. |
| `seed` | `null` → `42` | |
| `execution_profile` | `null` | GPU execution profile; falls back to the service default. |

### DPO-specific

| Field | Default | Notes |
|-------|---------|-------|
| `ref_policy_kl_penalty` | `0.05` | **β** in the DPO paper — strength of the KL penalty tying the policy to the reference model. Higher = stay closer to the reference. The main DPO knob. |
| `preference_loss_weight` | `1.0` | Weight on the preference (DPO) loss term. |
| `sft_loss_weight` | `0.0` | Weight on an auxiliary SFT regularization loss (`0` = pure DPO). Raise (e.g. `0.1`) to anchor the policy to the chosen responses. |
| `preference_average_log_probs` | `false` | Normalize preference log-probs by sequence length. |
| `sft_average_log_probs` | `false` | Normalize SFT-loss log-probs by sequence length. |
| `max_grad_norm` | `1.0` | Gradient clipping norm. |

### `parallelism`

Same block as automodel (`num_nodes`, `num_gpus_per_node`, `tensor_parallel_size`, `pipeline_parallel_size`, `context_parallel_size`, `sequence_parallel`). Divisibility rule (enforced by `RlJobOutput.validate_for_training`): `total_gpus = num_nodes × num_gpus_per_node` must be divisible by `tensor_parallel_size × pipeline_parallel_size × context_parallel_size`, and `batch_size` by `micro_batch_size × data_parallel_size`. **Multi-node (`num_nodes > 1`)** additionally requires the platform to set `NMP_RL_MULTINODE_SHARED_STORAGE_PATH` (shared filesystem for Ray's cross-node coordination); the compiler fails fast otherwise.

## Integrations (W&B / MLflow)

rl supports **W&B and MLflow** through the top-level `integrations` object (`integrations.wandb` / `integrations.mlflow`) — the same object shape used across all backends; full field reference in `hyperparameters.md` § **Integrations (all backends)**. rl specifics: the run name defaults to the **job id**, tags are auto-prefixed (`service:rl`, `framework:…`), and because rl runs on Kubernetes / Ray the `tracking_uri` / self-hosted W&B `base_url` must be reachable **from the cluster** (the local `docker0` recipe in `integrations-setup.md` is Docker-runtime only).

## DPO tuning guide

| Symptom | Action |
|---------|--------|
| Policy degenerates / drifts too far | Raise `ref_policy_kl_penalty` (β), e.g. `0.05` → `0.1`–`0.5`. |
| Barely changes from the reference | Lower β, or raise `learning_rate` one step (still keep it low for DPO). |
| Forgets base capabilities | Add SFT regularization: `sft_loss_weight` `0.1`–`0.5`. |
| CUDA OOM | Set `activation_checkpointing: true`; then lower `micro_batch_size`; then `max_seq_length`. |

