# Dataset formats (automodel)

Automodel detects schema from the **first JSONL line** (`DatasetSchema` in `services/automodel/.../datasets/preparation.py`).

Upload `train.jsonl` and optional `validation.jsonl` at the **fileset root**. Use the same fileset for `dataset.training` and `dataset.validation` in job JSON.

| Schema | JSONL shape | Job JSON |
|--------|-------------|----------|
| **CHAT** (preferred when model has chat template) | `{"messages": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}` | (none) |
| **SFT** | `{"prompt": "...", "completion": "..."}` | (none) |
| **CUSTOM** | Any two columns, e.g. `{"input": "...", "output": "..."}` | `"prompt_template": "{input} {output}"` on `dataset` |
| **EMBEDDING** | `{"query": "...", "pos_doc": "...", "neg_doc": ["...", "..."]}` | embedding training type when applicable |

**Conversion preference:** CHAT if `AutoTokenizer(...).chat_template` or model `spec.is_chat` / `spec.chat_template` → else SFT. Use CUSTOM or EMBEDDING only when the user asks or the task requires it.

For **CUSTOM**, placeholders in `prompt_template` must match column names exactly (two placeholders).
