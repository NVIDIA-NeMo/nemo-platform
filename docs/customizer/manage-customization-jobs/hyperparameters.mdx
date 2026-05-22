# Training Configuration

<a id="ft-hyperparameters"></a>
!!! tip
    Want to learn about training concepts at a high level? Check out the [Customization concepts](../about.md) page.

## Complete Schema Reference

For generated REST API details, see the [Customizer API Reference](../../api/index.md#tag-customizer) and
search for `CustomizationJobInput`.

Training is configured in the job's `spec.training` object.

## Quick Reference

The `training` field is a discriminated union on the `type` field. Each training method inherits common hyperparameters and adds method-specific fields.

### Training Method

| Parameter | Values | Description |
|-----------|--------|-------------|
| `training.type` | `sft`, `dpo`, `distillation` | Training method (discriminated union) |
| `training.peft` | `{ type: "lora", rank: 8, ... }` or omit | PEFT adapter configuration. If set, trains an adapter; if omitted, performs full-weight training |

For generated SFT schema details, see the [Customizer API Reference](../../api/index.md#tag-customizer)
and search for `SFTTrainingInput`.

### DPO Configuration

When `training.type` is `"dpo"`, additional DPO-specific fields are available:

| Parameter | Description | Recommended Values |
|-----------|-------------|-------------------|
| `ref_policy_kl_penalty` | KL divergence penalty (beta) | `0.05-0.5` |
| `preference_average_log_probs` | Average log probabilities for preference | `false` |
| `sft_average_log_probs` | Average log probabilities for SFT | `false` |
| `preference_loss_weight` | Weight for preference loss | `1.0` |
| `sft_loss_weight` | Weight for SFT loss | `0.0` |

For generated DPO schema details, see the [Customizer API Reference](../../api/index.md#tag-customizer)
and search for `DPOTrainingInput`.

!!! note
    PEFT (LoRA) is not yet supported with DPO training. Use full-weight training by omitting the `peft` field.

!!! tip
    When setting `val_check_interval` for DPO, use a fractional value (e.g., `0.5` for twice per epoch) or omit it entirely (validates once at end of epoch). Avoid integer step counts — they may not divide evenly into the total training steps, which can prevent validation from running on the final step.

### Parallelism Configuration

Parallelism parameters are grouped inside `training.parallelism`:

| Parameter | Description | Notes |
|-----------|-------------|-------|
| `parallelism.num_gpus_per_node` | Number of GPUs per node | Default: `1` |
| `parallelism.num_nodes` | Number of training nodes | Use 1 unless multi-node setup |
| `parallelism.tensor_parallel_size` | GPUs for tensor parallelism | Split layers across GPUs (for large models) |
| `parallelism.pipeline_parallel_size` | GPUs for pipeline parallelism | Split model stages across GPUs |
| `parallelism.context_parallel_size` | GPUs for context parallelism | For very long sequences |
| `parallelism.expert_parallel_size` | Expert parallelism for MoE models | Must divide number of experts |
| `parallelism.sequence_parallel` | Enable sequence parallelism | Memory optimization for long sequences |

!!! note
    **GPU Relationship**: `total_gpus = num_gpus_per_node x num_nodes`

    `data_parallel_size` is automatically derived as `total_gpus / (TP × PP × CP)`.

### PEFT / LoRA Configuration

To train a LoRA adapter, set `training.peft`:

| Parameter | Description | Recommended Values |
|-----------|-------------|-------------------|
| `peft.type` | PEFT method type | `"lora"` (currently the only supported method) |
| `peft.rank` | LoRA rank (low-rank dimension) | `8-64`. Higher = more capacity, more memory |
| `peft.alpha` | LoRA alpha scaling factor | `2-4× rank` (e.g., `32` for rank `8`) |
| `peft.dropout` | LoRA dropout probability | `0.0-0.1` for regularization |
| `peft.target_modules` | Module patterns to apply LoRA | `null` = all linear layers (default) |
| `peft.merge` | Merge LoRA weights into base model | `false` (default). If `true`, produces full-weight checkpoint |
| `peft.use_dora` | Enable DoRA (Weight-Decomposed Low-Rank Adaptation) | `false` (default) |

```python
"training": {
    "type": "sft",
    "peft": {
        "type": "lora",
        "rank": 8,
        "alpha": 32,
        "dropout": 0.0,
        "target_modules": ["*.q_proj", "*.v_proj"] # Optional: specific modules
    }
}
```

### Distillation Configuration

When `training.type` is `"distillation"`, additional KD-specific fields are available:

| Parameter | Description | Recommended Values |
|-----------|-------------|-------------------|
| `teacher_model` | Teacher model entity URN (`workspace/name`). Must share the same vocabulary and tokenizer as the student. | *(required)* |
| `teacher_precision` | Precision for loading the frozen teacher model | `bf16` (default). Use `fp16` or `fp32` if needed |
| `distillation_ratio` | Balance between CE loss and KD loss. `0.0` = CE only, `1.0` = KD only | `0.3–0.5` (start with `0.5`) |
| `distillation_temperature` | Softmax temperature for KD. Higher = softer probability distributions | `1.0–5.0` (start with `2.0`) |

For generated distillation schema details, see the
[Customizer API Reference](../../api/index.md#tag-customizer) and search for
`DistillationTrainingInput`.

<a id="kd-constraints"></a>
!!! note
    - Knowledge distillation uses **logit-pair distillation only** — the student learns to match the teacher's output probability distribution.
    - Both student and teacher models must be **full-weight Model Entities**. LoRA adapters cannot be used as teacher models.
    - Student and teacher must **share the same tokenizer and vocabulary**. Use models from the same family (e.g., Llama 3.2 1B Instruct + Llama 3.2 3B Instruct).
    - Both models are loaded during training. Plan GPU memory accordingly.

---

## Common Tuning Scenarios

### Loss Not Decreasing (Underfitting)

```python
"training": {
    "type": "sft",
    "peft": {"type": "lora"},
    "epochs": 5, # Increase from 3
    "learning_rate": 0.0001, # Increase from 5e-5
    "warmup_steps": 50 # Add warmup
}
```

### Out of Memory (OOM) Errors

```python
"training": {
    "type": "sft",
    "peft": {"type": "lora"},
    "batch_size": 8, # Reduce from 32
    "micro_batch_size": 1, # Reduce from 2
    "max_seq_length": 1024 # Reduce from 2048
}
```

### Overfitting (Validation Loss Increasing)

```python
"training": {
    "type": "sft",
    "peft": {
        "type": "lora",
        "rank": 8,
        "dropout": 0.1 # Add dropout
    },
    "epochs": 2, # Reduce from 5
    "learning_rate": 0.00002, # Lower to 2e-5
    "weight_decay": 0.01
}
```

---

## GPU Memory Guidelines

Estimated GPU requirements by model size:

| Model Size | LoRA (1 GPU) | Full FT (min GPUs) |
|------------|--------------|-------------------|
| 1B | 16GB | 1 × 24GB |
| 3B | 24GB | 2 × 24GB |
| 7-8B | 40GB | 2-4 × 80GB |
| 13B | 80GB | 4 × 80GB |
| 70B | 2 × 80GB | 8+ × 80GB |

!!! tip
    Use LoRA for most fine-tuning tasks. It's significantly more memory-efficient and often achieves comparable results to full fine-tuning.
