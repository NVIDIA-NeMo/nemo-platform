<!-- NeMo-RL (DPO + GRPO) job JSON reference. Index + source-of-truth: `hyperparameters.md`. Preference dataset formats: `dataset-formats.md` § NeMo-RL. -->

# NeMo-RL job JSON (DPO + GRPO)

The `rl` backend (`nemo customization rl submit`) runs on a Ray cluster — **Kubernetes runtime only**, full-weight (no LoRA). Schema: `RlJobInput` in `plugins/nemo-rl/src/nemo_rl_plugin/schema.py`. Run `nemo customization rl explain` for the live schema.

Discriminated by `training.type`: `"dpo"` or `"grpo"`.

## DPO job JSON layout

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
- `output.name` is the full-weight model entity the job registers. Output type is always `model` (no adapter).

## GRPO job JSON layout (NeMo Gym)

Convert a Prime Intellect hub env on an **internet-capable host** (no cluster hub egress):

```bash
pi-to-gym-conversion --hub-id primeintellect/ascii-tree --out-dir ./ascii-tree-pkg
```

Upload the env package as a FileSet with `purpose=environment` and the JSONL as `purpose=dataset`, then submit:

```json
{
  "model": "default/<model-entity>",
  "dataset": "default/<gym-jsonl-fileset>",
  "environment": "default/<environment-fileset>",
  "training": {
    "type": "grpo",
    "epochs": 1,
    "batch_size": 32,
    "micro_batch_size": 1,
    "num_generations_per_prompt": 8,
    "parallelism": { "num_nodes": 1, "num_gpus_per_node": 1 }
  },
  "output": { "name": "<output-name>" }
}
```

- `environment` is **required** for GRPO (adapter-wheels-v1 FileSet).
- `dataset` is Gym JSONL (`training.jsonl` required; not DPO preference triples).
- `sandboxed` is **not** a job field — platform config `NMP_RL_SANDBOXED_GYM_DEFAULT` (default `true`). Shared clusters fail closed until OpenSandbox is capable (`NMP_RL_SANDBOX_CLUSTER_CAPABLE=true`).

## Field reference — shared training knobs

### General

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
| `val_at_end` | `true` | Run a final validation pass after the last step. Keep enabled for best-checkpoint selection. |
| `keep_top_k` | `1` | Number of best checkpoints to retain. |
| `batch_size` | `32` | Global batch across all GPUs. |
| `micro_batch_size` | `1` | Per-GPU micro batch. |
| `max_seq_length` | `2048` | Max token sequence length. |
| `activation_checkpointing` | `false` | Recompute activations to cut memory. |
| `seed` | `null` → `42` | |
| `execution_profile` | `null` | GPU execution profile; falls back to the service default. |

### DPO-specific (`type: "dpo"`)

| Field | Default | Notes |
|-------|---------|-------|
| `ref_policy_kl_penalty` | `0.05` | **β** in the DPO paper — strength of the KL penalty tying the policy to the reference model. Higher = stay closer to the reference. The main DPO knob. |
| `preference_loss_weight` | `1.0` | Weight on the preference (DPO) loss term. |
| `sft_loss_weight` | `0.0` | Weight on an auxiliary SFT regularization loss (`0` = pure DPO). Raise (e.g. `0.1`) to anchor the policy to the chosen responses. |
| `preference_average_log_probs` | `false` | Normalize preference log-probs by sequence length. |
| `sft_average_log_probs` | `false` | Normalize SFT-loss log-probs by sequence length. |
| `max_grad_norm` | `1.0` | Gradient clipping norm. |

### GRPO-specific (`type: "grpo"`)

| Field | Default | Notes |
|-------|---------|-------|
| `num_generations_per_prompt` | `8` | Group size for relative advantages. |
| `num_prompts_per_step` | `null` | Derived from `batch_size / num_generations_per_prompt` when omitted. |
| `num_val_generations_per_prompt` | `4` | Generations per prompt at validation. |
| `normalize_rewards` | `true` | |
| `max_rollout_turns` | `1` | Multi-turn rollouts; most math envs use `1`. |
| `ref_policy_kl_penalty` | `0.0` | KL coefficient in the GRPO loss. |
| `ratio_clip_min` / `ratio_clip_max` | `0.2` / `0.28` | PPO-style ratio clip bounds. |

### `parallelism`

Same block as automodel (`num_nodes`, `num_gpus_per_node`, `tensor_parallel_size`, `pipeline_parallel_size`, `context_parallel_size`, `sequence_parallel`). Divisibility rule (enforced by `RlJobOutput.validate_for_training`): `total_gpus = num_nodes × num_gpus_per_node` must be divisible by `tensor_parallel_size × pipeline_parallel_size × context_parallel_size`, and `batch_size` by `micro_batch_size × data_parallel_size`. **Multi-node (`num_nodes > 1`)** additionally requires the platform to set `NMP_RL_MULTINODE_SHARED_STORAGE_PATH` (shared filesystem for Ray's cross-node coordination); the compiler fails fast otherwise.

## Integrations (W&B / MLflow)

rl supports **W&B and MLflow** through the top-level `integrations` object (`integrations.wandb` / `integrations.mlflow`) — the same object shape used across all backends; full field reference in `hyperparameters.md` § **Integrations (all backends)**. rl specifics: the run name defaults to the **job id**, tags are auto-prefixed (`service:rl`, `framework:…`), and because rl runs on Kubernetes / Ray the `tracking_uri` / self-hosted W&B `base_url` must be reachable **from the cluster** (the local `docker0` recipe in `integrations-setup.md` is Docker-runtime only).

## DPO tuning guide

| Symptom | Action |
|---------|--------|
| Policy degenerates / drifts too far | Raise `ref_policy_kl_penalty` (β), e.g. `0.05` → `0.1`–`0.5`. |
| Barely changes from the reference | Lower β, or raise `learning_rate` one step (still keep it low for DPO). |
| OOM | Enable `activation_checkpointing: true`; lower `batch_size` / `max_seq_length`. |
| Instability | Lower LR; raise β; check preference data quality. |
