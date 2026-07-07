# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Dataset profiler: sampled rows from fileset storage → DatasetProfile.

Reads a small deterministic sample from each data file via the storage
backend — byte-range probes for large JSONL (a few hundred KiB per file, never
a full download), whole reads only for small files — groups files by
column-set signature, and infers structure (JSON Schema + HF Features),
statistics (HF /statistics taxonomy), and semantics (detected format, scored
training-task candidates, ambiguities).

Determinism is a contract: the profile is written into fileset metadata, so
identical files must yield an identical profile (no timestamps, no random
sampling, deterministic group order). Controllers key re-profiling on
``source.files_hash``.

Parquet files are skipped for now (recorded in ``files_skipped``): row-group
sampling over remote storage needs the DuckDB path (see ``log_storage.py``)
or a job-tier profiler — follow-up.
"""

import csv
import dataclasses
import hashlib
import io
import json
import logging
import posixpath
from typing import Any, AsyncIterator, Optional

from nmp.common.files.dataset_profile import DatasetProfile

from nmp.core.files.app.backends.base import ByteRange, FileInfo, StorageImpl

logger = logging.getLogger(__name__)

PROFILER_NAME = "nmp-dataset-profiler"
PROFILER_VERSION = "0.4.0"
SCHEMA_VERSION = "2.1"

# HF /statistics promotes a string column to "string_label" at low cardinality;
# we mirror that so our column_type taxonomy matches theirs.
LABEL_CARDINALITY_MAX = 30
# ClassLabel names are written into the profile (i.e. into fileset metadata),
# so promotion is restricted to label-role columns with short values — never
# free-text columns whose sample happens to have low cardinality.
LABEL_VALUE_MAX_CHARS = 64

DEFAULT_SAMPLE_ROWS = 200
DEFAULT_STRATA = 8
PROBE_BYTES = 256 << 10  # per-stratum ranged read for large JSONL
STRATIFY_MIN_BYTES = 1 << 20  # JSONL below this is read whole
JSON_MAX_BYTES = 16 << 20  # whole-file JSON arrays above this are skipped
CSV_HEAD_BYTES = 256 << 10  # CSV stays head-only (quoted multi-line fields)
MAX_FILES = 2000  # hard cap; overflow reported in source.files_truncated

DATA_EXTENSIONS = (".jsonl", ".ndjson", ".json", ".csv", ".parquet")

# json files that are dataset packaging metadata, not row data
CONFIG_JSON_NAMES = {
    "dataset_infos.json",
    "dataset_dict.json",
    "config.json",
    "state.json",
    "tokenizer_config.json",
    "generation_config.json",
    "special_tokens_map.json",
}


# --------------------------------------------------------------------------- #
# Field-name normalization (semantic roles)
# --------------------------------------------------------------------------- #
FIELD_ALIASES: dict[str, str] = {
    # prompt side
    "prompt": "prompt",
    "instruction": "prompt",
    "question": "prompt",
    "query": "prompt",
    "input": "prompt",
    "context": "prompt",
    # completion side
    "completion": "completion",
    "response": "completion",
    "answer": "completion",
    "output": "completion",
    "target": "completion",
    "assistant": "completion",
    # chat
    "messages": "messages",
    "conversations": "messages",
    "conversation": "messages",
    # preference
    "chosen": "chosen",
    "rejected": "rejected",
    "chosen_response": "chosen",
    "rejected_response": "rejected",
    "response_a": "chosen",
    "response_b": "rejected",  # weak; disambiguated later
    # unpaired preference (KTO)
    "label": "label",
    "labels": "label",
    "score": "score",
    # embedding
    "anchor": "anchor",
    "positive": "positive",
    "negative": "negative",
    "pos": "positive",
    "neg": "negative",
    "negatives": "negatives",
    "sentence1": "sentence1",
    "sentence2": "sentence2",
    # raw text / pretrain
    "text": "text",
    "content": "text",
    "raw": "text",
    # RL verifiable reference
    "ground_truth": "ground_truth",
    "gold": "ground_truth",
    "reference": "ground_truth",
    "solution": "ground_truth",
    "verifiable_answer": "ground_truth",
    "test_cases": "ground_truth",
    # distillation
    "teacher_logits": "teacher_logits",
    "teacher_logprobs": "teacher_logits",
    "top_logprobs": "teacher_logits",
}


def _canon(name: str) -> str:
    return FIELD_ALIASES.get(name.strip().lower(), name.strip().lower())


# --------------------------------------------------------------------------- #
# Storage sampling
# --------------------------------------------------------------------------- #
class _SkipFile(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclasses.dataclass
class _FileSample:
    path: str
    size: int
    rows: list[dict]
    method: str  # head | stratified | even
    exact_rows: Optional[int]  # total rows, when knowable without a full scan


def files_hash(files: list[FileInfo]) -> str:
    """Content key over (path, size) of every file in the fileset listing.

    Controllers (and the profile endpoint) compare this against
    ``profile.source.files_hash`` to decide whether to re-profile.
    """
    h = hashlib.sha256()
    for f in sorted(files, key=lambda f: f.path):
        h.update(f"{f.path}:{f.size}\n".encode())
    return "sha256:" + h.hexdigest()


async def _read_bytes(storage: StorageImpl, path: str, byte_range: ByteRange | None) -> bytes:
    stream = storage.download(path, byte_range)
    if hasattr(stream, "__await__"):  # real backends return the iterator from a coroutine
        stream = await stream
    chunks: list[bytes] = []
    async for chunk in stream:  # type: ignore[union-attr]
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_jsonl_lines(data: bytes, n: int, *, drop_first: bool, at_eof: bool) -> list[dict]:
    lines = data.split(b"\n")
    if drop_first and lines:
        lines = lines[1:]  # partial line at the probe seek point
    if not at_eof and lines:
        lines = lines[:-1]  # partial line at the chunk boundary
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= n:
            break
    return out


async def _sample_jsonl(
    storage: StorageImpl, f: FileInfo, n: int
) -> tuple[list[dict], str, Optional[int]]:
    if f.size < STRATIFY_MIN_BYTES:
        data = await _read_bytes(storage, f.path, None)
        rows = _parse_jsonl_lines(data, n, drop_first=False, at_eof=True)
        all_rows = _parse_jsonl_lines(data, n + 1, drop_first=False, at_eof=True)
        exact = len(rows) if len(all_rows) <= n else None
        return rows, "head", exact
    # deterministic stratified byte-offset probes: sorted datasets must not
    # profile as single-valued, and re-runs must be byte-identical
    k = max(1, min(DEFAULT_STRATA, n))
    per = -(-n // k)
    out: list[dict] = []
    consumed_until = 0
    for i in range(k):
        if len(out) >= n:
            break
        off = f.size * i // k
        if off < consumed_until:
            continue  # previous probe already covered this offset
        end = min(off + PROBE_BYTES, f.size) - 1
        data = await _read_bytes(storage, f.path, ByteRange(off, end))
        out.extend(
            _parse_jsonl_lines(data, per, drop_first=off > 0, at_eof=end == f.size - 1)
        )
        consumed_until = end + 1
    return out[:n], "stratified", None


async def _sample_json(
    storage: StorageImpl, f: FileInfo, n: int
) -> tuple[list[dict], str, Optional[int]]:
    if f.size > JSON_MAX_BYTES:
        raise _SkipFile("json-too-large")
    obj = json.loads(await _read_bytes(storage, f.path, None))
    if isinstance(obj, dict) and isinstance(obj.get("data"), list):
        obj = obj["data"]
    if not isinstance(obj, list):
        # a single JSON object is packaging metadata, not row data
        raise _SkipFile("not-row-data")
    return _sample_evenly(obj, n), "even", len(obj)


def _coerce_csv_value(v: Any) -> Any:
    """CSV gives all-string values; recover ints/floats/bools/nulls so typed
    heuristics (categorical labels, numeric scores) work on CSV too."""
    if v is None or v == "":
        return None
    if not isinstance(v, str):
        return v
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


async def _sample_csv(
    storage: StorageImpl, f: FileInfo, n: int
) -> tuple[list[dict], str, Optional[int]]:
    # head-only: mid-file seeks can land inside quoted multi-line fields
    whole = f.size <= CSV_HEAD_BYTES
    end = (f.size if whole else CSV_HEAD_BYTES) - 1
    data = await _read_bytes(storage, f.path, ByteRange(0, end))
    text = data.decode("utf-8", errors="replace")
    if not whole:
        text = text[: text.rfind("\n") + 1]  # drop the partial trailing line
    rows: list[dict] = []
    for r in csv.DictReader(io.StringIO(text)):
        rows.append({k: _coerce_csv_value(v) for k, v in r.items() if k is not None})
        if len(rows) > n:
            break
    exact = len(rows) if whole and len(rows) <= n else None
    return rows[:n], "head", exact


def _sample_evenly(rows: list, n: int) -> list:
    if len(rows) <= n:
        return rows
    step = len(rows) // n
    return rows[::step][:n]


async def _sample_file(
    storage: StorageImpl, f: FileInfo, n: int
) -> tuple[list, str, Optional[int]]:
    low = f.path.lower()
    if low.endswith((".jsonl", ".ndjson")):
        return await _sample_jsonl(storage, f, n)
    if low.endswith(".json"):
        return await _sample_json(storage, f, n)
    if low.endswith(".csv"):
        return await _sample_csv(storage, f, n)
    if low.endswith(".parquet"):
        raise _SkipFile("parquet-not-yet-supported")
    raise _SkipFile("unknown-extension")


async def _collect_samples(
    storage: StorageImpl, files: list[FileInfo], sample_rows: int
) -> tuple[list[_FileSample], list[dict], int]:
    data_files = sorted(
        (f for f in files if f.path.lower().endswith(DATA_EXTENSIONS)),
        key=lambda f: f.path,
    )
    truncated = max(0, len(data_files) - MAX_FILES)
    data_files = data_files[:MAX_FILES]
    # every file gets at least one row: a rare-schema shard past the row
    # budget must still form its group
    per_file = max(1, sample_rows // len(data_files)) if data_files else 0
    samples: list[_FileSample] = []
    skipped: list[dict] = []
    for f in data_files:
        if posixpath.basename(f.path).lower() in CONFIG_JSON_NAMES:
            skipped.append({"path": f.path, "reason": "packaging-metadata"})
            continue
        try:
            rows, method, exact = await _sample_file(storage, f, per_file)
        except _SkipFile as e:
            skipped.append({"path": f.path, "reason": e.reason})
            continue
        except Exception:  # noqa: BLE001 - sniffing is best-effort by design
            logger.warning("profiler failed to read %s", f.path, exc_info=True)
            skipped.append({"path": f.path, "reason": "unreadable"})
            continue
        rows = [r for r in rows if isinstance(r, dict)]
        if not rows:
            skipped.append({"path": f.path, "reason": "no-rows"})
            continue
        samples.append(
            _FileSample(path=f.path, size=f.size, rows=rows, method=method, exact_rows=exact)
        )
    return samples, skipped, truncated


# --------------------------------------------------------------------------- #
# Grouping: one profile per column-set signature
# --------------------------------------------------------------------------- #
def _signature(s: _FileSample) -> frozenset:
    return frozenset(k for row in s.rows for k in row)


def _group_samples(samples: list[_FileSample]) -> list[dict]:
    """Group files by column signature; subset signatures (shards missing an
    optional column) merge into the larger group. Deterministic order:
    largest group by bytes first."""
    groups: list[dict] = []
    for s in sorted(samples, key=lambda s: (-len(_signature(s)), s.path)):
        sig = _signature(s)
        target = next((g for g in groups if sig <= g["sig"]), None)
        if target is None:
            target = {"sig": set(sig), "samples": []}
            groups.append(target)
        target["samples"].append(s)
    groups.sort(key=lambda g: (-sum(s.size for s in g["samples"]), sorted(g["sig"])))
    return groups


# --------------------------------------------------------------------------- #
# Layer 1 — structure: HF Features (interop) + JSON Schema (platform-native)
# --------------------------------------------------------------------------- #
_INT = {"dtype": "int64", "_type": "Value"}
_FLOAT = {"dtype": "float64", "_type": "Value"}
_STRING = {"dtype": "string", "_type": "Value"}


def _value_type(v: Any) -> Optional[dict]:
    """Map one python value to a serialized datasets.Features type (subset)."""
    if isinstance(v, bool):
        return {"dtype": "bool", "_type": "Value"}
    if isinstance(v, int):
        return dict(_INT)
    if isinstance(v, float):
        return dict(_FLOAT)
    if isinstance(v, str):
        return dict(_STRING)
    if isinstance(v, dict):
        return {k: _value_type(x) or dict(_STRING) for k, x in v.items()}
    if isinstance(v, list):
        elem = _value_type(v[0]) if v else dict(_STRING)
        # list-of-struct serializes as [ {field: type, ...} ]; list-of-scalar
        # as a Sequence — matching HF /info
        if isinstance(elem, dict) and "_type" not in elem:
            return [elem]
        return {"feature": elem, "_type": "Sequence"}
    return None  # None / unknown — decided by other rows


def _widen(a: dict | list, b: dict | list) -> dict:
    if a in (_INT, _FLOAT) and b in (_INT, _FLOAT):
        return dict(_FLOAT)  # JSON-serialized numerics routinely mix 1 and 1.5
    return dict(_STRING)


def infer_features(rows: list[dict]) -> dict:
    """Infer a serialized ``datasets.Features`` mapping from sampled rows.

    Conservative subset: Value(bool/int64/float64/string), nested structs,
    Sequence, and ClassLabel promotion for low-cardinality label-role columns.
    Mixed types widen (int/float → float64, anything else → string).
    """
    types: dict[str, dict | list | None] = {}
    string_vals: dict[str, set[str]] = {}
    for rec in rows:
        for k, v in rec.items():
            t = _value_type(v)
            if t is None:
                types.setdefault(k, None)
                continue
            prev = types.get(k)
            if prev is None:
                types[k] = t
            elif prev != t:
                types[k] = _widen(prev, t)
            if isinstance(v, str):
                string_vals.setdefault(k, set()).add(v)

    features: dict[str, Any] = {}
    n = len(rows)
    for k, t in types.items():
        t = t or dict(_STRING)
        # ClassLabel promotion — label-role columns only: `names` embeds actual
        # data values in the profile, which must never happen for free-text
        # columns (short-answer completions, PII). Other low-cardinality string
        # columns still surface as string_label (values-free) in statistics.
        vals = string_vals.get(k)
        if (
            t == _STRING
            and vals
            and _canon(k) == "label"
            and len(vals) <= min(LABEL_CARDINALITY_MAX, max(2, n // 5))
            and all(len(v) <= LABEL_VALUE_MAX_CHARS for v in vals)
        ):
            features[k] = {"names": sorted(vals), "_type": "ClassLabel"}
        else:
            features[k] = t
    return features


_JSON_TYPE_BY_DTYPE = {
    "bool": "boolean",
    "int64": "integer",
    "float64": "number",
    "string": "string",
}


def _feature_to_json_schema(t: dict | list) -> dict:
    if isinstance(t, list):  # list-of-struct
        return {"type": "array", "items": _feature_to_json_schema(t[0])}
    ftype = t.get("_type")
    if ftype == "Value":
        return {"type": _JSON_TYPE_BY_DTYPE.get(t.get("dtype"), "string")}
    if ftype == "ClassLabel":
        return {"type": "string", "enum": t["names"]}
    if ftype == "Sequence":
        return {"type": "array", "items": _feature_to_json_schema(t["feature"])}
    # nested struct
    return {
        "type": "object",
        "properties": {k: _feature_to_json_schema(v) for k, v in t.items()},
    }


def features_to_json_schema(features: dict, stats: list[dict]) -> dict:
    """One-row JSON Schema from inferred features + observed nulls.

    Sample-derived and advisory: `required` lists columns never seen missing
    or null; columns with observed nulls get a nullable type instead.
    """
    nan_by_col = {
        s["column_name"]: s["column_statistics"].get("nan_count", 0) for s in stats
    }
    props: dict[str, Any] = {}
    required: list[str] = []
    for col, t in features.items():
        sch = _feature_to_json_schema(t)
        if nan_by_col.get(col, 0):
            if isinstance(sch.get("type"), str):
                sch["type"] = [sch["type"], "null"]
        else:
            required.append(col)
        props[col] = sch
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": props,
    }
    if required:
        schema["required"] = sorted(required)
    return schema


# --------------------------------------------------------------------------- #
# Layer 2 — statistics: datasets-server /statistics shape (minimal subset)
# --------------------------------------------------------------------------- #
def compute_statistics(rows: list[dict], features: dict) -> list[dict]:
    """Per-column stats using HF's column_type taxonomy.

    Kept small: column_type, nan stats, n_unique for label-ish columns, and
    length summaries for text/list columns.
    """
    n = len(rows)
    stats: list[dict] = []
    for col, ftype in features.items():
        vals = [r.get(col) for r in rows]
        nan_count = sum(1 for v in vals if v is None)
        present = [v for v in vals if v is not None]
        col_stats: dict[str, Any] = {
            "nan_count": nan_count,
            "nan_proportion": round(nan_count / n, 5) if n else 0.0,
        }

        if isinstance(ftype, list) or (
            isinstance(ftype, dict) and ftype.get("_type") == "Sequence"
        ):
            ctype = "list"
            lengths = [len(v) for v in present if isinstance(v, list)]
            if lengths:
                col_stats.update(
                    min=min(lengths),
                    max=max(lengths),
                    mean=round(sum(lengths) / len(lengths), 3),
                )
        elif isinstance(ftype, dict) and ftype.get("_type") == "ClassLabel":
            ctype = "class_label"
            col_stats["n_unique"] = len({str(v) for v in present})
        elif isinstance(ftype, dict) and ftype.get("_type") == "Value":
            dtype = ftype.get("dtype")
            if dtype == "string":
                uniq = {v for v in present if isinstance(v, str)}
                # HF splits string columns into label-like vs free-text by cardinality
                if (
                    uniq
                    and len(uniq) <= LABEL_CARDINALITY_MAX
                    and len(uniq) < max(2, len(present))
                ):
                    ctype = "string_label"
                    col_stats["n_unique"] = len(uniq)
                else:
                    ctype = "string_text"
                    lens = [len(v) for v in present if isinstance(v, str)]
                    if lens:
                        col_stats.update(
                            min=min(lens),
                            max=max(lens),
                            mean=round(sum(lens) / len(lens), 3),
                        )
            elif dtype in ("int64", "float64", "bool"):
                ctype = {"int64": "int", "float64": "float", "bool": "bool"}[dtype]
                nums = [
                    v
                    for v in present
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                ]
                if dtype in ("int64", "float64") and nums:
                    col_stats.update(
                        min=min(nums),
                        max=max(nums),
                        mean=round(sum(nums) / len(nums), 5),
                    )
                if dtype == "int64":
                    col_stats["n_unique"] = len({v for v in present})
            else:
                ctype = "string_text"
        else:  # nested struct
            ctype = "dict"

        stats.append(
            {"column_name": col, "column_type": ctype, "column_statistics": col_stats}
        )
    return stats


# --------------------------------------------------------------------------- #
# Layer 3 — semantics (NMP extension)
# --------------------------------------------------------------------------- #
ASSISTANT_ROLE_VALUES = {"assistant", "gpt", "model", "bot"}


def _looks_like_chat(v: Any) -> bool:
    return (
        isinstance(v, list)
        and bool(v)
        and isinstance(v[0], dict)
        and ("role" in v[0] or "from" in v[0])
    )


def _chat_signals(rows: list[dict], roles: dict[str, str]) -> tuple[bool, bool]:
    """(is chat, has assistant turns). Chat SFT needs assistant turns to learn
    from; user-only conversations are prompt datasets for RL, not SFT."""
    for col, r in roles.items():
        if r != "messages":
            continue
        chat_rows = [rec.get(col) for rec in rows if _looks_like_chat(rec.get(col))]
        if len(chat_rows) < max(1, int(0.6 * len(rows))):
            continue
        with_assistant = sum(
            1
            for msgs in chat_rows
            if any(
                isinstance(m, dict)
                and str(m.get("role") or m.get("from") or "").lower()
                in ASSISTANT_ROLE_VALUES
                for m in msgs
            )
        )
        return True, with_assistant >= max(1, int(0.6 * len(chat_rows)))
    return False, False


def infer_semantics(rows: list[dict], features: dict, stats: list[dict]) -> dict:
    """Canonical roles, detected format, scored task candidates, ambiguities."""
    by_col = {s["column_name"]: s for s in stats}
    roles = {col: _canon(col) for col in features}
    f = set(roles.values())

    def col_type(role: str) -> Optional[str]:
        for col, r in roles.items():
            if r == role:
                return by_col.get(col, {}).get("column_type")
        return None

    chat_ok, chat_has_assistant = _chat_signals(rows, roles)
    label_categorical = any(
        s["column_type"] in ("class_label", "string_label", "bool")
        or (
            s["column_type"] == "int"
            and s["column_statistics"].get("n_unique", 999) <= LABEL_CARDINALITY_MAX
        )
        for s in stats
        if roles[s["column_name"]] == "label"
    )
    score_float = col_type("score") in ("float", "int")
    has_ground_truth = "ground_truth" in f

    fmt = "unknown"
    cands: list[dict] = []
    ambiguities: list[str] = []

    def cand(task: str, conf: float, reason: str) -> None:
        cands.append({"task": task, "confidence": conf, "reason": reason})

    def set_fmt(value: str) -> None:
        nonlocal fmt
        if fmt == "unknown":
            fmt = value

    # -- preference / RM ------------------------------------------------------
    if {"chosen", "rejected"} <= f:
        # aligns with the RL backend's BinaryPreferenceDataset
        set_fmt("preference_binary")
        cand("dpo", 0.65, "prompt/chosen/rejected pairs => preference optimization")
        cand("reward_model", 0.65, "same shape trains a Bradley-Terry reward model")
        ambiguities.append(
            "DPO vs reward-model: identical data shape — needs user intent "
            "or a model-side signal (value head) to disambiguate."
        )
    # KTO needs a completion to judge; label + prompt alone is classification-shaped
    kto_shape = (
        "label" in f
        and "completion" in f
        and label_categorical
        and "text" not in f
        and "chosen" not in f
    )
    if kto_shape:
        set_fmt("unpaired_preference")
        cand("kto", 0.6, "prompt/completion + binary label => unpaired preference (KTO)")

    # -- distillation ---------------------------------------------------------
    if "teacher_logits" in f:
        cand("offline_logit_kd", 0.85, "teacher-logit column => offline logit distillation")

    # -- embedding ------------------------------------------------------------
    has_negative = bool({"negative", "negatives"} & f)
    if has_negative and ("anchor" in f or "positive" in f):
        set_fmt("embedding_triplet")
        cand("embedding", 0.85, "triplet (anchor/positive/negative) => embedding/biencoder")
    elif "anchor" in f and "positive" in f:
        # positive pairs only — contrastive training with in-batch negatives
        set_fmt("embedding_pair")
        cand("embedding", 0.8, "anchor/positive pairs (no negatives) => embedding, in-batch negatives")
    elif {"sentence1", "sentence2"} <= f and score_float:
        set_fmt("embedding_pair_scored")
        cand("embedding", 0.8, "sentence pairs + numeric score => embedding (STS)")

    # -- sequence classification ----------------------------------------------
    if label_categorical and "chosen" not in f and not kto_shape:
        if "text" in f:
            set_fmt("text_classification")
            cand("seq_cls", 0.75, "text + categorical label => sequence classification")
        elif "prompt" in f and not ({"completion", "messages"} & f):
            set_fmt("text_classification")
            cand(
                "seq_cls",
                0.65,
                "prompt-like text + categorical label, no responses => sequence classification",
            )

    # -- SFT / pretrain / prompt-only -----------------------------------------
    if chat_ok and chat_has_assistant:
        set_fmt("chat_messages")
        cand("sft", 0.85, "chat `messages` with assistant turns => chat SFT")
    elif chat_ok:
        # user-only conversations: a prompt dataset in chat clothing
        set_fmt("chat_messages")
        if has_ground_truth:
            cand("rlvr", 0.7, "prompt-only chat + verifiable ground_truth => RL w/ verifiable rewards")
        else:
            cand("grpo", 0.6, "chat `messages` without assistant turns => prompts for on-policy RL")
        ambiguities.append(
            "Chat messages contain no assistant turns — nothing to SFT on; "
            "the reward source (reward fn / verifier / environment) is "
            "external to the dataset — confirm one exists."
        )
    elif "completion" in f and "prompt" in f:
        set_fmt("prompt_completion")
        # a categorical label alongside prompt/completion signals KTO, not plain SFT
        conf = 0.5 if kto_shape else 0.8
        cand(
            "sft",
            conf,
            "prompt/completion pairs => instruction SFT"
            + (" (demoted: categorical label suggests KTO)" if kto_shape else ""),
        )
    elif "text" in f and not any(c["task"] in ("seq_cls", "embedding") for c in cands):
        set_fmt("text_corpus")
        cand("continued_pretrain", 0.6, "raw `text` only => continued pretraining")
    elif "prompt" in f and not ({"completion", "chosen", "messages"} & f):
        set_fmt("prompt_with_ground_truth" if has_ground_truth else "prompt_only")
        if has_ground_truth:
            cand("rlvr", 0.7, "prompt + verifiable ground_truth, no responses => RL w/ verifiable rewards")
            ambiguities.append(
                "Prompt-only dataset implies RL; confirm a verifier exists for the ground_truth column."
            )
        elif label_categorical:
            cand(
                "grpo",
                0.4,
                "prompt-only with categorical label — RL prompts possible, but the label suggests classification",
            )
        else:
            cand("grpo", 0.6, "prompt-only (no responses) => on-policy RL (GRPO/PPO family)")
            ambiguities.append(
                "Prompt-only dataset implies RL; the reward source (reward fn / "
                "verifier / environment) is external to the dataset — confirm one exists."
            )

    if not cands:
        ambiguities.append(
            f"Schema did not match a known training format; roles seen: {sorted(f)}."
        )

    # de-dup by task keeping max confidence, sort desc
    best: dict[str, dict] = {}
    for c in cands:
        if c["task"] not in best or c["confidence"] > best[c["task"]]["confidence"]:
            best[c["task"]] = c
    ordered = sorted(best.values(), key=lambda c: -c["confidence"])
    if (
        len(ordered) >= 2
        and abs(ordered[0]["confidence"] - ordered[1]["confidence"]) < 0.1
        and not ambiguities
    ):
        ambiguities.append(
            f"Top candidates are close ({ordered[0]['task']} vs {ordered[1]['task']})."
        )

    return {
        "canonical_roles": {
            c: r
            for c, r in roles.items()
            if r != c
            or r
            in {
                "prompt",
                "completion",
                "messages",
                "chosen",
                "rejected",
                "label",
                "score",
                "text",
                "anchor",
                "positive",
                "negative",
                "negatives",
                "sentence1",
                "sentence2",
                "ground_truth",
                "teacher_logits",
            }
        },
        "detected_format": fmt,
        "task_candidates": ordered,
        "ambiguities": ambiguities,
    }


# --------------------------------------------------------------------------- #
# Profile assembly
# --------------------------------------------------------------------------- #
async def profile_fileset_storage(
    storage: StorageImpl,
    *,
    sample_rows: int = DEFAULT_SAMPLE_ROWS,
    files: list[FileInfo] | None = None,
) -> DatasetProfile:
    """Profile a fileset's files directly from its storage backend.

    Pass ``files`` when the caller already holds the listing (avoids a second
    ``list_files`` round-trip and guarantees the hash matches what the caller
    compared for idempotency).
    """
    if files is None:
        files = await storage.list_files(None)
    samples, skipped, truncated = await _collect_samples(storage, files, sample_rows)
    groups_out: list[dict] = []
    for i, g in enumerate(_group_samples(samples)):
        rows = [r for s in g["samples"] for r in s.rows]
        feats = infer_features(rows)
        stats = compute_statistics(rows, feats)
        sem = infer_semantics(rows, feats, stats)
        methods = {s.method for s in g["samples"]}
        strategy = (
            "stratified" if "stratified" in methods else "even" if "even" in methods else "head"
        )
        exact = [s.exact_rows for s in g["samples"]]
        groups_out.append(
            {
                "name": f"group-{i}",
                "files": sorted(s.path for s in g["samples"]),
                "columns": sorted(g["sig"]),
                "sampling": {
                    "strategy": strategy,
                    "strata": DEFAULT_STRATA if "stratified" in methods else None,
                    "rows_sampled": len(rows),
                },
                "structure": {
                    "row_schema": features_to_json_schema(feats, stats),
                    "features": feats,
                    # exact only when every member file's count is knowable
                    # (fully-read small files); else consumers fall back to
                    # fileset accounting
                    "num_rows": sum(exact)
                    if exact and all(e is not None for e in exact)
                    else None,
                    "num_bytes": sum(s.size for s in g["samples"]),
                },
                "statistics": stats,
                "semantics": sem,
            }
        )
    return DatasetProfile.model_validate(
        {
            "schema_version": SCHEMA_VERSION,
            # no timestamp anywhere: identical files must yield an identical
            # profile (no metadata churn, no controller re-trigger loops)
            "profiler": {
                "name": PROFILER_NAME,
                "version": PROFILER_VERSION,
                "method": "sampled",
                "sampled_rows": sum(len(s.rows) for s in samples),
            },
            "source": {
                "kind": "storage",
                "path": "",
                "files_hash": files_hash(files),
                "files_skipped": skipped,
                "files_truncated": truncated,
            },
            "groups": groups_out,
            "primary": groups_out[0]["name"] if groups_out else None,
        }
    )
