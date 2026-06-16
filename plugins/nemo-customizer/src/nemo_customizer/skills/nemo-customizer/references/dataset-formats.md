# Dataset formats

Both backends read JSONL from a platform fileset, but the **row shape and the job-JSON dataset block differ**. Pick the section that matches your plugin.

Upload `train.jsonl` and optional `validation.jsonl` at the **fileset root**. For automodel use the same fileset for `dataset.training` and `dataset.validation`. For unsloth use `dataset.path` (and `dataset.validation_path`).

## Automodel

Automodel detects schema from the **first JSONL line** (`DatasetSchema` in `services/automodel/.../datasets/preparation.py`).

| Schema | JSONL shape | Job JSON |
|--------|-------------|----------|
| **CHAT** (preferred when model has chat template) | `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` | (none) |
| **SFT** | `{"prompt": "...", "completion": "..."}` | (none) |
| **CUSTOM** | Any two columns, e.g. `{"input": "...", "output": "..."}` | `"prompt_template": "{input} {output}"` on `dataset` |
| **EMBEDDING** | `{"query": "...", "pos_doc": "...", "neg_doc": ["...", "..."]}` | embedding training type when applicable |

**Conversion preference:** CHAT if `AutoTokenizer(...).chat_template` or model `spec.is_chat` / `spec.chat_template` → else SFT. Use CUSTOM or EMBEDDING only when the user asks or the task requires it.

For **CUSTOM**, placeholders in `prompt_template` must match column names exactly (two placeholders).

## Unsloth

Unsloth has no schema auto-detection — the row shape is controlled by two `dataset` fields in the job JSON. The training driver hands rows to `trl.SFTTrainer`, which only reads one column (`text_field`) per row.

| Mode | `dataset.apply_chat_template` | Required JSONL shape | What the trainer sees |
|------|------------------------------|----------------------|----------------------|
| **Messages (preferred)** | `true` | `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` (same as automodel CHAT) | Each row's `messages` is rendered through `tokenizer.apply_chat_template(...)` at training time; the rendered string is written into `text_field` (default `"text"`). |
| **Pre-rendered text** | `false` (default) | `{"text": "<one fully-formed training string>"}` | The string in `text_field` is fed to SFTTrainer verbatim. |

Job JSON snippets:

```json
"dataset": { "path": "default/<dataset-fileset>", "apply_chat_template": true }
```

```json
"dataset": { "path": "default/<dataset-fileset>", "text_field": "text", "apply_chat_template": false }
```

Optional fields on the unsloth `dataset` block:

| Field | Default | Notes |
|-------|---------|-------|
| `validation_path` | `null` | Same ref shape as `path` (`"name"` or `"workspace/name"`). |
| `text_field` | `"text"` | Column the trainer reads. In messages mode it's the column the rendered string is **written to** before training. |
| `apply_chat_template` | `false` | Set `true` only when each row has a `messages` array. |
| `packing` | `false` | `trl.SFTTrainer` packing — concatenates short rows up to `max_seq_length` for throughput. Needs short, compatible rows; safe to leave off. |

**Conversion guidance:**

- If the model has a chat template (`AutoTokenizer.from_pretrained(...).chat_template` is truthy), use the same `to_chat` converter from `references/hf-conversion.md` and set `apply_chat_template: true`. This is the recommended path for instruction-tuned models.
- If the model has **no** chat template, render each example to a single training string yourself (e.g. `f"{prompt}\n{completion}"`) and emit `{"text": "..."}` rows. Then set `apply_chat_template: false` and keep `text_field: "text"`.
- The automodel SFT format `{"prompt": "...", "completion": "..."}` is **not** directly consumable by unsloth — unsloth has no built-in `prompt`/`completion` concatenation. Convert to either messages or pre-rendered text before upload.

EMBEDDING and CUSTOM (automodel-only schemas) are not supported by unsloth today.

## Post-training evaluation

Eval rows must use the **same CHAT `messages` shape** as training. Do not flatten to `prompt`/`expected` for the evaluator.

| Training JSONL | Eval dataset | Eval `prompt_template` | Metric reference |
|----------------|--------------|------------------------|------------------|
| `messages` (single- or multi-turn) | Same fileset split (`validation.jsonl`) | `messages[:-1]` — exclude final assistant label — see `post-training-eval.md` | `{{ item.messages[-1].content }}` |

LoRA inference and eval use the **provider** gateway on the **base** entity (`/provider/<name>/-/v1`, `model: default--<adapter>`). Base model uses the model-entity path. Full SFT / merged checkpoints use the **output** model entity's model-entity URL — deploy first. See `post-training-eval.md` and the **Using the adapter** / **Using the fine-tuned model** sections in `SKILL.md`.

Shared helpers and compare CLI: `references/eval_helpers.py`. Full workflow: `references/post-training-eval.md`.
