# Hugging Face dataset conversion

Run from **nemo-platform** git root: `uv run python …` (plugin brings `datasets` + `transformers`).

Do **not** ask the user for local paths when they gave an HF dataset id — convert and upload in the same session.

## Chat-template check

```python
from transformers import AutoTokenizer
has_chat = bool(getattr(AutoTokenizer.from_pretrained("<hf-repo>", trust_remote_code=True), "chat_template", None))
```

If the model entity already exists: `nemo models get <entity> --workspace default` → use `spec.is_chat` or `spec.chat_template` instead of re-downloading tokenizer weights.

## Conversion script (adapt `to_chat` per dataset)

```python
from datasets import load_dataset
from transformers import AutoTokenizer
import json
from pathlib import Path

HF_REPO = "<hf-repo>"
HF_DATASET = "<hf-dataset>"   # e.g. tau/commonsense_qa
DATASET_NAME = HF_DATASET.split("/")[-1].lower()   # fileset name, e.g. commonsense_qa

has_chat = bool(getattr(AutoTokenizer.from_pretrained(HF_REPO, trust_remote_code=True), "chat_template", None))

def to_chat(ex):
    # MCQA example (tau/commonsense_qa):
    labels, texts = ex["choices"]["label"], ex["choices"]["text"]
    choices = "\n".join(f"{l}. {t}" for l, t in zip(labels, texts))
    user = f"Question: {ex['question']}\nChoices:\n{choices}\nAnswer:"
    assistant = texts[labels.index(ex["answerKey"])]
    return {"messages": [{"role": "user", "content": user}, {"role": "assistant", "content": assistant}]}

def to_sft(ex):
    row = to_chat(ex)
    return {"prompt": row["messages"][0]["content"], "completion": row["messages"][1]["content"]}

convert = to_chat if has_chat else to_sft

ds = load_dataset(HF_DATASET)
out = Path("/tmp/train-data")
out.mkdir(exist_ok=True)
for split in ("train", "validation"):
    if split in ds:
        with (out / f"{split}.jsonl").open("w") as f:
            for ex in ds[split]:
                f.write(json.dumps(convert(ex)) + "\n")
```

Then upload (see main skill). Validate with `nemo files list <DATASET_NAME> --workspace default`.
