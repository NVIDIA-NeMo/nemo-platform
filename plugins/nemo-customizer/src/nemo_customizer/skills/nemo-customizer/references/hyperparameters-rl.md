<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

<!-- NeMo-RL (DPO + GRPO) job JSON reference. Index + source-of-truth: `hyperparameters.md`. Preference dataset formats: `dataset-formats.md` § NeMo-RL. -->

# NeMo-RL job JSON (DPO + GRPO)

The `rl` backend (`nemo customization rl submit`) runs on a Ray cluster — **Kubernetes runtime only**, full-weight (no LoRA). Schema: `RlJobInput` in `plugins/nemo-rl/src/nemo_rl_plugin/schema.py`. Run `nemo customization rl explain` for the live schema.

Discriminated by `training.type`: `"dpo"` or `"grpo"`. **`training.type` is required** — it is the union discriminator, so a payload that omits it is rejected with `union_tag_not_found` rather than defaulting to DPO.

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
- `sandboxed` is **not** a job field — platform config `NMP_RL_SANDBOXED_GYM_DEFAULT` (default `true`). Shared clusters fail closed until OpenSandbox is capable (`NMP_PLATFORM_SANDBOX_CLUSTER_CAPABLE=true`) and `NMP_RL_JOB_STORAGE_PVC_CLAIM` names the job-storage PVC the Gym sandbox re-mounts for the environment and dataset. Both are compile-time checks.

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
| `val_at_end` | `true` | Run a final validation pass after the last step. Keep enabled: it makes the final checkpoint carry validation metrics so best-checkpoint selection (`metric_name`/`keep_top_k`) works — otherwise NeMo-RL warns and falls back to the latest checkpoint. Set `false` only to skip the extra eval. **GRPO:** ignored when the dataset ships no `validation.jsonl` — the compiler disables validation rather than fail in `setup()`. |
| `keep_top_k` | `1` | Number of best checkpoints to retain (DPO ranks by validation loss; GRPO by `val:total_reward/mean`). |
| `batch_size` | `32` | Global batch across all GPUs. **DPO:** preference **pairs**. **GRPO:** must divide `num_prompts_per_step × num_generations_per_prompt` — see the GRPO table. |
| `micro_batch_size` | `1` | Per-GPU micro batch. |
| `max_seq_length` | `2048` | Max token sequence length. |
| `activation_checkpointing` | `false` | Recompute activations in the backward pass to cut memory — the first knob to enable for OOM / larger models / longer sequences. |
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
| `num_prompts_per_step` | `null` | Derived from `batch_size / num_generations_per_prompt` when omitted. `num_prompts_per_step × num_generations_per_prompt` must be a multiple of `batch_size` (enforced by `validate_for_training`), so prefer a `num_generations_per_prompt` that divides `batch_size`. |
| `automodel_kwargs` | `null` | Passed to `policy.dtensor_cfg.automodel_kwargs` (selects the DTensor v2 backend). `{"force_hf": true}` loads stock HuggingFace modules when a model's custom Automodel backbone is not compatible with the parallelizer; a `{"backend": {...}}` block picks the Transformer-Engine / DeepEP MoE implementation. |
| `router_aux_loss_coef` | `null` | MoE router auxiliary-loss coefficient, applied as a HuggingFace config override. Set `0.0` for RL on a MoE model — the aux load-balancing loss is a pretraining regularizer and adds a gradient term unrelated to the reward. |
| `vllm_tensor_parallel_size` | `null` | Tensor parallelism for the rollout engine alone. Defaults to `min(parallelism.tensor_parallel_size, parallelism.num_gpus_per_node)`. Set it when the model needs several GPUs to hold inference weights but you want the policy trained at a different tensor-parallel size. |
| `vllm_gpu_memory_utilization` | `0.5` | Fraction of each GPU vLLM reserves for weights plus KV cache. Raise toward `0.7` for large models, which otherwise cannot load their weight shard. |
| `val_at_start` | `false` | Run validation **before** the first training step. Enable to measure uplift: baseline and result come from one job on the same data and generation settings, instead of a separate baseline run that must be kept in sync. Costs a full rollout pass, hence off by default. Ignored without a `validation.jsonl`. **GRPO only** — DPO always validates at step 0, since its validation needs no generation. |
| `max_new_tokens` | `null` → `max_seq_length` | Cap on tokens generated per rollout turn. **Known limitation:** NeMo Gym's `verifiers_agent` does not yet honour this — see below. |
| `normalize_rewards` | `true` | |
| `overlong_filtering` | `false` | Zero the loss contribution of rollouts truncated at the generation cap, so the policy is not penalised for responses it was cut off from finishing. Enable when many rollouts are truncated. |
| `max_rollout_turns` | `1` | Multi-turn rollouts; most math envs use `1`. |
| `ref_policy_kl_penalty` | `0.0` | KL coefficient in the GRPO loss. |
| `ratio_clip_min` / `ratio_clip_max` | `0.2` / `0.28` | PPO-style ratio clip bounds. |
| `max_grad_norm` | `1.0` | Gradient clipping norm. |

### `parallelism`

Same block as automodel (`num_nodes`, `num_gpus_per_node`, `tensor_parallel_size`, `pipeline_parallel_size`, `context_parallel_size`, `sequence_parallel`), plus `expert_parallel_size` for MoE policy training (GRPO only; read by the DTensor v2 backend, and setting it above `1` selects v2). Divisibility rule (enforced by `RlJobOutput.validate_for_training`): `total_gpus = num_nodes × num_gpus_per_node` must be divisible by `tensor_parallel_size × pipeline_parallel_size × context_parallel_size × expert_parallel_size`, and `batch_size` by `micro_batch_size × data_parallel_size`. **Multi-node (`num_nodes > 1`)** additionally requires the platform to set `NMP_RL_MULTINODE_SHARED_STORAGE_PATH` (shared filesystem for Ray's cross-node coordination); the compiler fails fast otherwise.

### Known limitation: `max_new_tokens` does not reach the agent

The compiler stamps `max_new_tokens` onto `policy.generation.max_new_tokens`, and NeMo-RL puts it on every rollout row as `responses_create_params.max_output_tokens`. NeMo Gym's `verifiers_agent` then **drops it** — it reads `max_tokens` from its own environment config instead. The effective per-turn cap is therefore `min(agent max_tokens, max_seq_length - prompt_len)`, the second term applied by vLLM's `_clamp_max_tokens`.

This is not fatal, because the cap is a minimum of the two and `max_seq_length` is under your control. But until the agent honours `max_output_tokens`, bound response length through `max_seq_length`, or through `max_tokens` in the environment package's own config — not through `max_new_tokens`.

### How validation sampling works

There is no validation counterpart to `num_generations_per_prompt`. NeMo-RL's `validate()` runs **exactly one rollout per row** of `validation.jsonl` — no per-prompt fan-out. To score a prompt *k* times (mean@k), repeat its **row** *k* times when building the dataset. Validation cost is therefore just the row count, and `val_at_start` / `val_at_end` score the same rows, which makes the before/after comparison paired.

## Integrations (W&B / MLflow)

rl supports **W&B and MLflow** through the top-level `integrations` object (`integrations.wandb` / `integrations.mlflow`) — the same object shape used across all backends; full field reference in `hyperparameters.md` § **Integrations (all backends)**. rl specifics: the run name defaults to the **job id**, tags are auto-prefixed (`service:rl`, `framework:…`), and because rl runs on Kubernetes / Ray the `tracking_uri` / self-hosted W&B `base_url` must be reachable **from the cluster** (the local `docker0` recipe in `integrations-setup.md` is Docker-runtime only).

## DPO tuning guide

| Symptom | Action |
|---------|--------|
| Policy degenerates / drifts too far | Raise `ref_policy_kl_penalty` (β), e.g. `0.05` → `0.1`–`0.5`. |
| Barely changes from the reference | Lower β, or raise `learning_rate` one step (still keep it low for DPO). |
| Forgets base capabilities (DPO) | Add SFT regularization: `sft_loss_weight` `0.1`–`0.5`. |
| CUDA OOM | Set `activation_checkpointing: true`; then lower `micro_batch_size`; then `max_seq_length`. **GRPO:** also lower `num_generations_per_prompt` (keeping `batch_size` divisible). |
| Instability | Lower LR; raise β. **DPO:** check preference data quality. **GRPO:** check reward scale and `ratio_clip_max`. |
