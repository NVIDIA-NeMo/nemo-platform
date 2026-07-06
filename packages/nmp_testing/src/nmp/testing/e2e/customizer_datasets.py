# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dataset preparation + platform-resource setup for customizer GPU e2e tests.

Downloads small slices of public HuggingFace datasets, converts them to the JSONL
shapes each backend expects, uploads them to platform filesets, and registers the
base HF model entity. Kept separate from :mod:`nmp.testing.e2e.customizer` (job /
deploy helpers) so the heavy ``datasets`` import stays lazy and out of unrelated
test collection.

Dataset contracts (see ``plugins/nemo-customizer/.../references/dataset-formats.md``):

- **SFT/LoRA (automodel, unsloth)** — CHAT ``messages`` JSONL. ``rajpurkar/squad``
  rows become ``{"messages": [system, user(context+question), assistant(answer)]}``.
  The final assistant turn is the eval label.
- **DPO (rl)** — raw ``nvidia/HelpSteer3`` preference rows
  (``{context, response1, response2, overall_preference}``) written unchanged to a
  single fileset as ``training.jsonl`` + ``validation.jsonl``.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from nemo_platform import NeMoPlatform
from nemo_platform.types.files import HuggingfaceStorageConfigParam
from nmp.testing.e2e.customizer import wait_for_model_spec

logger = logging.getLogger(__name__)

SQUAD_HF_DATASET = "rajpurkar/squad"
HELPSTEER_HF_DATASET = "nvidia/HelpSteer3"
HELPSTEER_CONFIG = "preference"

# System prompt kept identical between training and eval so the eval label
# (final assistant turn) is what the fine-tuned model learns to produce.
_SQUAD_SYSTEM_PROMPT = (
    "You are a helpful assistant that answers questions using only the provided context. "
    "Answer with the shortest exact span from the context."
)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    """Write ``rows`` as JSONL to ``path``; return the number of rows written."""
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
            count += 1
    return count


def _squad_to_chat(example: dict[str, Any]) -> dict[str, Any]:
    """Convert a SQuAD row to a CHAT ``messages`` row (answer = first gold span)."""
    answers = example.get("answers") or {}
    texts = answers.get("text") or [""]
    answer = texts[0] if texts else ""
    user = f"Context: {example['context']}\n\nQuestion: {example['question']}"
    return {
        "messages": [
            {"role": "system", "content": _SQUAD_SYSTEM_PROMPT},
            {"role": "user", "content": user},
            {"role": "assistant", "content": answer},
        ]
    }


def prepare_squad_chat_dataset(
    out_dir: Path | str,
    n_train: int = 3000,
    n_val: int = 300,
    seed: int = 42,
) -> tuple[Path, Path]:
    """Download ``rajpurkar/squad`` and write CHAT ``train.jsonl`` / ``validation.jsonl``.

    Returns:
        ``(train_path, validation_path)``.
    """
    from datasets import load_dataset

    # `datasets` return types are a loose union; treat handles as Any (map-style
    # Datasets support .shuffle/.select/len at runtime).
    ds: Any = load_dataset(SQUAD_HF_DATASET)
    train = ds["train"].shuffle(seed=seed).select(range(min(n_train, len(ds["train"]))))
    val = ds["validation"].shuffle(seed=seed).select(range(min(n_val, len(ds["validation"]))))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    train_path = out / "train.jsonl"
    val_path = out / "validation.jsonl"
    n_tr = _write_jsonl(train_path, (_squad_to_chat(row) for row in train))
    n_va = _write_jsonl(val_path, (_squad_to_chat(row) for row in val))
    logger.info("Prepared SQuAD CHAT dataset: %d train / %d val rows in %s", n_tr, n_va, out)
    return train_path, val_path


def _helpsteer_rows(split: Any, n: int, seed: int) -> Iterator[dict[str, Any]]:
    """Yield ``n`` raw HelpSteer3 preference rows (only the fields rl consumes)."""
    subset = split.shuffle(seed=seed).select(range(min(n, len(split))))
    for row in subset:
        yield {
            "context": row["context"],
            "response1": row["response1"],
            "response2": row["response2"],
            "overall_preference": row["overall_preference"],
        }


def prepare_helpsteer_dpo_dataset(
    out_dir: Path | str,
    n_train: int = 3000,
    n_val: int = 300,
    seed: int = 42,
) -> tuple[Path, Path]:
    """Download ``nvidia/HelpSteer3`` (preference) → raw ``training.jsonl`` / ``validation.jsonl``.

    rl auto-detects the HelpSteer3 schema, so rows are written unchanged. When the
    dataset exposes no ``validation`` split, the val slice is taken from the tail of
    ``train`` (disjoint from the train slice).

    Returns:
        ``(training_path, validation_path)``. Note the rl backend requires these
        exact filenames at the fileset root.
    """
    from datasets import load_dataset

    ds: Any = load_dataset(HELPSTEER_HF_DATASET, HELPSTEER_CONFIG)
    train_split: Any = ds["train"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    training_path = out / "training.jsonl"
    validation_path = out / "validation.jsonl"

    if "validation" in ds:
        n_tr = _write_jsonl(training_path, _helpsteer_rows(train_split, n_train, seed))
        n_va = _write_jsonl(validation_path, _helpsteer_rows(ds["validation"], n_val, seed))
    else:
        # Slice disjoint train/val from the single split.
        shuffled = train_split.shuffle(seed=seed)
        take_train = min(n_train, len(shuffled))
        take_val = min(n_val, max(0, len(shuffled) - take_train))
        train_rows = (_project_helpsteer(shuffled[i]) for i in range(take_train))
        val_rows = (_project_helpsteer(shuffled[i]) for i in range(take_train, take_train + take_val))
        n_tr = _write_jsonl(training_path, train_rows)
        n_va = _write_jsonl(validation_path, val_rows)

    logger.info("Prepared HelpSteer3 DPO dataset: %d train / %d val rows in %s", n_tr, n_va, out)
    return training_path, validation_path


def _project_helpsteer(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "context": row["context"],
        "response1": row["response1"],
        "response2": row["response2"],
        "overall_preference": row["overall_preference"],
    }


def _as_messages(context: Any) -> list[dict[str, str]]:
    """Normalize a HelpSteer3 ``context`` (str or message list) to a message list."""
    if isinstance(context, str):
        return [{"role": "user", "content": context}]
    return [{"role": msg["role"], "content": msg["content"]} for msg in context]


def prepare_dpo_eval_rows(validation_path: Path | str) -> list[dict[str, Any]]:
    """Build CHAT eval rows from a HelpSteer3 validation split.

    Each row becomes ``{"messages": [*context, {"role": "assistant", "content": preferred}]}``
    where *preferred* is ``response1`` when ``overall_preference < 0`` else ``response2``.
    Ties (``overall_preference == 0``) are dropped — they have no single label.
    Used as the deterministic DPO uplift proxy: a DPO-aligned model should overlap the
    preferred response more than the base model does (F1/ROUGE, not exact match).
    """
    rows: list[dict[str, Any]] = []
    for line in Path(validation_path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        preference = record.get("overall_preference", 0)
        if preference == 0:
            continue
        preferred = record["response1"] if preference < 0 else record["response2"]
        messages = _as_messages(record["context"])
        messages.append({"role": "assistant", "content": preferred})
        rows.append({"messages": messages})
    return rows


# --------------------------------------------------------------------------- #
# Platform resource setup
# --------------------------------------------------------------------------- #
def create_dataset_fileset(
    sdk: NeMoPlatform,
    workspace: str,
    name: str,
    files: dict[str, Path],
) -> str:
    """Create a ``dataset`` fileset and upload ``{remote_path: local_path}`` files.

    Returns the fileset name.
    """
    sdk.files.filesets.create(workspace=workspace, name=name, purpose="dataset", exist_ok=True)
    for remote_path, local_path in files.items():
        sdk.files.upload(
            fileset=name,
            workspace=workspace,
            local_path=str(local_path),
            remote_path=remote_path,
        )
    listing = sdk.files.list(fileset=name, workspace=workspace)
    logger.info("Uploaded %d files to dataset fileset %s/%s", len(listing.data), workspace, name)
    return name


def create_hf_model_entity(
    sdk: NeMoPlatform,
    workspace: str,
    entity: str,
    hf_repo: str,
    revision: str = "main",
    token_secret: str | None = None,
    wait_timeout: int = 600,
) -> str:
    """Register an HF-backed weights fileset + model entity, then wait for its spec.

    The platform runs a background model-spec-analysis job when a fileset-backed
    entity is created; training/deploy need ``entity.spec`` populated, so we block on
    :func:`wait_for_model_spec`.

    Returns the model-entity name.
    """
    weights_fileset = f"{entity}-weights"
    storage: HuggingfaceStorageConfigParam = {
        "type": "huggingface",
        "repo_id": hf_repo,
        "repo_type": "model",
        "revision": revision,
    }
    if token_secret:
        storage["token_secret"] = token_secret

    sdk.files.filesets.create(
        workspace=workspace,
        name=weights_fileset,
        purpose="model",
        storage=storage,
        exist_ok=True,
    )
    sdk.models.create(
        workspace=workspace,
        name=entity,
        fileset=f"{workspace}/{weights_fileset}",
        custom_fields={"hf_model_id": hf_repo},
        exist_ok=True,
    )
    wait_for_model_spec(sdk, workspace, entity, timeout=wait_timeout)
    logger.info("Registered model entity %s/%s from HF repo %s", workspace, entity, hf_repo)
    return entity
