# Post-training evaluation (train/eval format parity)

Use after a customization job reaches **`completed`** when the user wants to compare **base vs LoRA** on the validation split.

## Format contract

Training and evaluation must use the **same CHAT JSONL row shape**:

```json
{
  "messages": [
    {"role": "user", "content": "Question: …\nChoices:\n…\nAnswer:"},
    {"role": "assistant", "content": "bank"}
  ]
}
```

Multi-turn rows use the same rule: the **final** `messages[-1]` turn is the assistant label; all preceding turns are context.

| Do | Don't |
|----|-------|
| Pass rows with `messages` unchanged from the training fileset | Flatten to `prompt` / `expected` or `prompt` / `completion` for eval |
| Send **`messages[:-1]`** at inference (exclude only the final assistant label) | Pass full `messages` including the label turn, or use `{"messages": "{{ item.messages }}"}` unfiltered |
| Score against **`messages[-1].content`** (final assistant turn) | Score against a renamed `expected` field unless you also keep `messages` |

Single-turn MCQA (user + assistant) is the degenerate case: `messages[:-1]` is just the user turn.

Automodel and unsloth both train on this shape when `has_chat` is true (see `hf-conversion.md`, `dataset-formats.md`).

## Evaluator templates (required)

```python
CHAT_USER_PROMPT_TEMPLATE = {
    "messages": "{{ item.messages[:-1] }}",
}
CHAT_REFERENCE_TEMPLATE = "{{ item.messages[-1].content }}"
```

Import from `references/eval_helpers.py` — do not re-type these in one-off scripts.

## Inference defaults (Qwen3 / thinking models)

| Setting | Recommended | Avoid |
|---------|-------------|-------|
| `enable_thinking` | `false` via `chat_template_kwargs` for short-answer SFT | Thinking on without enough tokens — model never closes ``, strip hook fails |
| `max_tokens` | `64` (short assistant labels) | `16` with thinking on; `1024` thinking on without strip (verbose prose) |
| System prompt | Omit unless user asks — matches training | Extra system prompt changes decode path vs SFT |

For thinking-enabled eval, set `reasoning=ReasoningParams(end_token="")` **and** ensure `max_tokens` is large enough for the model to emit the end token before generating the answer.

## Inference after customization (wrap-up)

Include this in the **Using the adapter** section of every completed customization report. Agents must discover `<provider>` from `nemo inference providers list --workspace default -f json` and fill concrete URLs — do not leave placeholders.

### LoRA adapters load automatically

After a customization job reaches **`completed`**, the platform registers the adapter on the base **model entity**. On a deployment with **`lora_enabled: true`**, enabled adapters are **hot-reloaded automatically** (adapter sidecar → vLLM). **Do not** update the deployment, re-create providers, or add the adapter to a `served_models` list before post-training eval — run eval as soon as the job completes.

| Prerequisite (one-time) | Per-adapter step after training |
|-------------------------|----------------------------------|
| A **READY** inference deployment for the base model entity with `lora_enabled: true` | Confirm adapter appears under `nemo models get <model-entity>` → `adapters` |
| Gateway reachable at the model-entity URL below | Target the adapter by name in the eval request (see table) |

### Request routing (base vs LoRA)

The model-entity proxy path **always** resolves to the base VirtualModel. Setting `"model": "default--<adapter-name>"` on `/model/<base-entity>/-/v1` does **not** select the adapter — gateway logs will show only the base path.

| Target | Gateway route | URL pattern | Request `model` field |
|--------|---------------|-------------|------------------------|
| Base entity | **Model entity** | `{NEMO_BASE_URL}/apis/inference-gateway/v2/workspaces/default/model/<model-entity>/-/v1` | `default/<model-entity>` |
| LoRA adapter | **Provider** | `{NEMO_BASE_URL}/apis/inference-gateway/v2/workspaces/default/provider/<provider>/-/v1` | `default--<adapter-name>` |

`eval_helpers.py` auto-discovers a READY provider that serves the base entity (or pass `--provider <name>`). Adapter weights still hot-reload on the deployment — no provider update per adapter.

Optional sanity checks:

- `nemo models get <model-entity> --workspace default` — adapter listed with `enabled: true`
- `nemo inference providers list --workspace default` — provider status **READY**
- LoRA eval/inference logs should show `path=…/provider/<provider>/-/v1/chat/completions`, **not** `…/model/<model-entity>/-/v1`
- JSON output includes `warnings` when routing looks wrong or adapter scores match base within ~1.5 pp

### Why earlier evals looked wrong

If base and LoRA scores were identical (~99% same outputs), the adapter was almost certainly called through the **model-entity** path. That path always resolves to the base VirtualModel — the `"model": "default--<adapter>"` field in the body is ignored. Fix: route LoRA through the **provider** URL with the same `model` field. `eval_helpers.build_platform_model_target()` and the CLI implement this split automatically.

### MCQA metric interpretation

For commonsense_qa-style MCQA, treat **`normalized_accuracy`** as the primary metric (`normalize_mcqa_answer` strips `A. foo` / markdown).

| Observation | Likely meaning |
|-------------|----------------|
| Base & LoRA both ~59% normalized, within ~1 pp | LoRA hit **model-entity** path (base only) — check `warnings` and gateway logs |
| Base raw exact 0%, normalized ~59% | Normal for base on MCQA (formatted prose answers) |
| LoRA normalized >> base (e.g. 76% vs 59%) | Correct provider routing and real adapter lift |
| Train loss dropped sharply but eval flat | Wrong eval routing or need more epochs — val loss ≠ accuracy |

### Epoch / adapter ablations

Resolve adapter names from completed job specs instead of guessing:

```python
from eval_helpers import list_completed_job_adapters, compare_adapters, build_eval_payload

jobs = list_completed_job_adapters(
    base_url="http://10.0.0.51:8080",
    workspace="default",
    model_entity="qwen3-1.7b",
    dataset_fileset="commonsense_qa",
)
# jobs[0].epochs, jobs[0].adapter_name, jobs[0].backend — sorted newest first

summaries = compare_adapters(
    base_url="...",
    workspace="default",
    model_entity="qwen3-1.7b",
    adapter_names=[jobs[0].adapter_name, jobs[2].adapter_name],
    rows=rows,
)
payload = build_eval_payload(..., summaries=summaries, adapter_names=[...])
# payload["lift_vs_base"], payload.get("warnings")
```

When comparing adapters from **different backends** (automodel vs unsloth) or batch configs, note confounds — epoch count alone may not explain the gap.

### Production chat requests (same rules as eval)

| Piece | LoRA adapter | Base model |
|-------|--------------|------------|
| HTTP base URL | `…/provider/<provider>/-/v1` | `…/model/<model-entity>/-/v1` |
| `"model"` | `default--<adapter-name>` | `default/<model-entity>` |
| `messages` | `messages[:-1]` from the training row (exclude final assistant label) | Same |
| Qwen3 short SFT | `"chat_template_kwargs": {"enable_thinking": false}` | Same |
| `max_tokens` / `temperature` | `64` / `0` typical for short labels | Same |

CLI shortcuts (substitute names from the job):

```bash
# LoRA
nemo inference gateway provider post v1/chat/completions <provider> --workspace default \
  --body '{"model":"default--<adapter>","messages":[{"role":"user","content":"…"}],"max_tokens":64,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'

# Base
nemo inference gateway model post v1/chat/completions <model-entity> --workspace default \
  --body '{"model":"default/<model-entity>","messages":[{"role":"user","content":"…"}],"max_tokens":64,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}'
```

## Metrics

| Task | Metrics |
|------|---------|
| MCQA / exact label | `ExactMatchMetric` + `normalize_mcqa_answer()` when models return `A. foo` or markdown |
| Similarity | `ROUGEMetric`, `BLEUMetric` with `CHAT_REFERENCE_TEMPLATE` |

Val loss from training is **not** accuracy — always run a generation eval for user-facing quality.

## Helper script

From **nemo-platform** git root:

```bash
# Base vs one adapter
uv run python plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/references/eval_helpers.py \
  --base-url http://10.0.0.51:8080 \
  --model-entity qwen3-1.7b \
  --adapter qwen3-1.7b-csqa-unsloth-jun16-e3 \
  --provider qwen3-1.7b-csqa-lora-deploy \
  --dataset-fileset commonsense_qa \
  --split validation.jsonl \
  --output /tmp/fine-tune-eval.json

# Base vs multiple adapters (epoch ablation)
uv run python plugins/nemo-customizer/src/nemo_customizer/skills/nemo-customizer/references/eval_helpers.py \
  --base-url http://10.0.0.51:8080 \
  --model-entity qwen3-1.7b \
  --adapter qwen3-1.7b-commonsense-qa-lora-jun12-v2 \
  --adapter qwen3-1.7b-csqa-unsloth-jun16-e3 \
  --dataset-fileset commonsense_qa \
  --split validation.jsonl \
  --output /tmp/fine-tune-eval-multi.json
```

Programmatic use:

```python
from eval_helpers import (
    load_chat_jsonl_from_platform,
    compare_adapters,
    compare_base_vs_adapter,
    build_eval_payload,
    list_completed_job_adapters,
    routing_sanity_warnings,
    CHAT_USER_PROMPT_TEMPLATE,
)
```

(Add `references/` to `sys.path` or run via `uv run python` from repo root.)

## Report to user

After compare, report for **base and each adapter**:

- **Normalized accuracy** (primary for MCQA)
- Raw exact match (strict string — often 0% on base for formatted answers)
- Lift vs base (`lift_vs_base` in JSON output)
- ROUGE / BLEU aggregates if requested
- Any `warnings` from routing sanity checks
- Inference settings (`enable_thinking`, `max_tokens`) and dataset fileset ref

Uses the **nemo-evaluator SDK** (`Evaluator`, metrics, `RunConfigOnlineModel`) under the hood — no separate evaluator skill doc required. For general BYOB/rubric eval outside customization, use the **nemo-evaluator** skill.
