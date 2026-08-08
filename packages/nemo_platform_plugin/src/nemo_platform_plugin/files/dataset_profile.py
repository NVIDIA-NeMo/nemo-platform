# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The stored contract for the dataset profiler.

A ``DatasetProfile`` is machine-owned metadata the profiler computes once, at the Files layer, so
every consumer reads one typed description of a dataset instead of downloading and re-inspecting it.

The profile has two stored layers:

* **structure** — predominantly facts: file layout, splits, the derived row schema (``features``),
  and per-column ``stats``. The one detected attribute living here is the ``FeatureSchema.semantic_role``
  marker stacked on the feature node it describes.
* **classification** — an objective description of what the data *is*: ``dataset_type``, the
  ``format`` / ``prompt_form`` axes, and ``verifiability``.

Vocabularies (``dataset_type``, ``semantic_role``, ``modality``, ...) are open ``str`` values with
documented canonical sets, not closed enums: only known values are emitted, but consumers must
tolerate unknown ones so the vocabulary can grow without a breaking change. Pydantic's default
``extra="ignore"`` gives the same forward-compatibility for unknown *fields*.

**Why this lives in a shared package rather than with the profiler that writes it.** The Files
service is a first-class consumer, not a bystander: it stores a profile as its own entity and serves
it, so its entities, endpoints and schemas all need this type. Were the contract to live in the
datasets plugin, a core service would depend on an optional plugin to deserialize rows in its own
database — a deployment that installs no profiler still holds stored profiles and still answers
``GET .../filesets/{name}/profile``. Keeping it here means neither side depends on the other: the
module is pydantic-only, with no platform dependencies, so the profiler imports it standalone while
Files imports it as the type it persists.

It sits under ``files/`` because Files is what stores and serves it, alongside the rest of that
service's shared contract — including ``metadata.py``, which houses the equally dataset-shaped
``DatasetMetadataContent``. Note that a profile is *not* carried inside fileset metadata: it is a
separate entity, so writing one cannot clobber an unrelated metadata edit that lands between a read
and a write.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

# Semver of THIS contract. Gates consumer compatibility: new detectors or vocabulary values are a
# minor bump; a change to the fields below is a major bump. Still 1.0 because nothing consumes it
# yet — the fields have moved a great deal, but pre-release churn is not a break for anyone, and the
# first number that means something is the one shipped alongside the first consumer.
PROFILE_SCHEMA_VERSION = "1.0"


# ---- classification: an objective description of what the data is (computed, stored) -----------


class Evidence(BaseModel):
    """Why the profiler believes what it detected.

    Captured at profile time — the only moment it is cheap and guaranteed to match the stored
    result; once the data or the profiler version moves, a re-run explains the *new* snapshot, not
    the stored one.
    """

    kind: str = Field(
        description=(
            "column_name | column_dtype | content_probe | split_name | file_name | card_metadata | "
            "user_hint | error — `user_hint` for a caller-supplied column role the data could not "
            "support, and `error` for when a detector could not run at all, so an absent finding is "
            "distinguishable from a finding of absence."
        ),
    )
    detail: str = Field(
        description="Self-describing evidence, e.g. \"answer matches '#### <number>' in 100% of 1024 sampled rows\".",
    )


class Verifiability(BaseModel):
    """A found verification target. Present only when one exists; absence *is* the claim (not verifiable)."""

    method: str = Field(
        description="extractable_final_answer | ground_truth_column | constraint | test_cases",
    )
    coverage: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of sampled rows with a usable verification target.",
    )
    evidence: list[Evidence] = Field(default_factory=list)


class PartitionClassification(BaseModel):
    """What the data *is*, described objectively — the stored basis a downstream reader uses to decide
    which tasks the dataset can train.

    Holds the partition-level findings only: column-level semantics are the ``semantic_role`` markers
    on the feature nodes they describe, but the evidence for *why* they were assigned is recorded here.
    """

    modality: str = Field(default="text", description="text | image_text | audio_text | ...")
    dataset_type: str = Field(
        description=(
            "Dataset-type vocabulary (prompt_completion, preference_pair, ...). A SUMMARY, not the "
            "basis for a decision — it is the most specific single structure the roles satisfy, and a "
            "dataset routinely satisfies several. The `semantic_role` markers are what a consumer "
            "should match on; `candidates` lists everything this one is a projection of."
        ),
    )
    candidates: list[str] = Field(
        default_factory=list,
        description=(
            "Every dataset type the assigned roles satisfy, most specific first, so "
            "`candidates[0] == dataset_type`. prompt + completion + score + label is genuinely both "
            "scored_response and unpaired_preference; reporting only the first made rule order an "
            "invisible tie-break and hid that the data supports more than one use. Deliberately not a "
            'capability list ("supports DPO") — trainer requirements shift and differ per framework, '
            "so that mapping belongs in the consumer, computed from the roles."
        ),
    )
    format: str | None = Field(default=None, description="standard | conversational | mixed")
    prompt_form: str | None = Field(default=None, description="explicit | implicit | n/a")
    verifiability: Verifiability | None = Field(
        default=None,
        description="Present only when a verification target was found; keeps its own coverage-scoped evidence.",
    )
    evidence: list[Evidence] = Field(
        default_factory=list,
        description=(
            "Why the type / roles / axes were assigned: one flat list, detail strings self-describe "
            "what they support. A profile-time snapshot; unrecoverable once the data or profiler version move."
        ),
    )


# ---- structure: facts + the stacked semantic_role detection (computed) -------------------------


class Quantiles(BaseModel):
    """A per-row distribution summary. p99 = long-tail sequence-length signal; max = hard cap.

    The shape is the point, not the precision. Mean and max cannot tell "uniformly medium-length"
    apart from "mostly short with a long tail", and those call for opposite sequence budgets — set
    one from `max` and most of the memory is wasted, set it from the mean and the tail is silently
    truncated. Reading p50 against p99 is what answers it.

    **p50 / p95 / p99 are estimates, within a couple of percent.** They are read off counters bucketed
    by magnitude rather than from the lengths themselves, which is what keeps the profiler's memory
    flat in rows. Every row is counted, so the *rank* is exact; only the value is rounded, and it is
    rounded to a bound that does not grow with the dataset. That is the cheap error to accept here,
    because whoever reads these rounds to a power of two anyway.

    **`max` is exact**, always, and is the only number here safe to treat as a hard bound.
    """

    p50: int
    p95: int
    p99: int
    max: int


class TextStats(BaseModel):
    """Measurements for a ``string`` column."""

    chars: Quantiles = Field(description="Per-row character-length distribution.")


class MessageStats(BaseModel):
    """Measurements for a ``messages`` column (a list of ``{role, content}``)."""

    turns: Quantiles = Field(description="Per-row turn count (p99 -> packing long chats).")
    content_chars: Quantiles = Field(description="Per-row total content length -> chat sequence length.")
    roles_seen: list[str] = Field(
        default_factory=list,
        description=(
            'The distinct role strings actually present in the sampled rows, verbatim — e.g. ["system", '
            '"user", "assistant", "tool"], but equally ShareGPT\'s ["human", "gpt"] or a house convention. '
            "A measurement of row content, not a vocabulary the profiler picks from, so it is deliberately "
            "not an enum: an unexpected role is the finding worth reporting, and normalizing or dropping it "
            "would hide exactly what a consumer needs to see before choosing a chat template. "
            "Bounded: this is fed straight from row content, and a column with more distinct roles "
            "than fit here is not a chat column, which the first few dozen already say."
        ),
    )
    ends_with_assistant_rate: float = Field(
        ge=0.0,
        le=1.0,
        description="Key signal separating an SFT target (conversation ends on an assistant turn) from a prompt-only row.",
    )
    valid_alternation_rate: float = Field(ge=0.0, le=1.0)
    has_tool_calls: bool = False


class NumericStats(BaseModel):
    """Measurements for a numeric column."""

    min: float
    max: float
    mean: float


class TextQuality(BaseModel):
    """Corruption signals for a text column. Flags training-wrecking data, not toxicity / PII.

    **Estimates, not counts**, and the only measurements in the profile that are. These three are
    all the per-character work there is — every other statistic is O(1) per row, and the content
    probes are literal searches costing a fraction of these — so scanning every row of a large
    column costs more than the entire rest of the profile. They are also ratios, which a sample of
    tens of thousands of rows pins down far past the precision anyone reads them to. Bounding them
    is what makes reading every row of a dataset affordable.

    The sample is contiguous blocks, spaced evenly across the column: deterministic, so two runs over
    the same bytes agree, and spread rather than taken from the head, so a sorted shard does not
    decide the answer. Blocks rather than every n-th row because an even step aliases against
    periodic data — a set that round-robins over sources, or carries k responses per prompt, is
    periodic by construction, and a step sharing a factor with that period samples one phase and
    only that phase. A column smaller than the bound is measured in full.
    """

    whitespace_ratio: float = Field(ge=0.0, le=1.0, description="Padding / bad scraping.")
    non_ascii_ratio: float = Field(ge=0.0, le=1.0, description="Encoding / non-Latin signal.")
    repetition_score: float = Field(ge=0.0, le=1.0, description="Degenerate repeated-substring loops.")


class FeatureSchema(BaseModel):
    """One node of the row schema, derived de novo from the data (there is no external JSON-Schema
    store to reference). Carries the measured layout (name, dtype, children) plus at most one
    detected ``semantic_role`` marker stacked on the same node.

    Recursive and fully expanded: a ``struct`` node has child ``fields``; a ``list`` / ``messages``
    node has an element ``items`` — for ``messages`` the per-message ``{role, content}`` struct is
    spelled out, so a vision message whose content is a list of typed parts shows up structurally.
    The column-level chat summary lives in ``MessageStats`` on the stats side. This tree is the
    clean, bridgeable schema artifact (e.g. to a JSON Schema or a UI columns view).
    """

    name: str = Field(default="", description='Column / struct-field name; "" for a list element.')
    dtype: str = Field(
        description=(
            "string | bool | int8..int64 / uint8..uint64 | float16/32/64 | struct | list | messages | "
            "image | audio | video | json | ... — fixed-width numeric widths as the source file reports them."
        ),
    )
    semantic_role: str | None = Field(
        default=None,
        description=(
            "Detected role (from the role vocabulary), valid at any depth of the tree; omitted when nothing "
            "was detected. The only detected attribute in the structure layer — its evidence lands in "
            "PartitionClassification.evidence. Named `semantic_role`, not `role`, so it never collides with a "
            "message struct's `role` key."
        ),
    )
    semantic_role_source: str | None = Field(
        default=None,
        description=(
            "Where `semantic_role` came from: detected | declared. A declared role was supplied by the "
            "caller and only accepted because the dtype could carry it; a detected one was inferred from "
            "the column name. Kept as a field rather than left to evidence prose because the distinction "
            "is per-column and actionable — a UI renders a declared role as confirmed and a detected one "
            "as a suggestion to correct."
        ),
    )
    fields: list[FeatureSchema] | None = Field(default=None, description="dtype == struct: named child fields.")
    items: FeatureSchema | None = Field(default=None, description="dtype in {list, messages}: element schema.")

    @model_validator(mode="after")
    def _fields_and_items_are_exclusive(self) -> FeatureSchema:
        """A node is either a named-field container or has a single element schema, never both.

        Deliberately the only structural check here: it holds for *any* dtype, so it costs no
        forward compatibility. Tying `fields` / `items` to specific dtype values would instead
        reject a profile written by a newer profiler that added a container dtype, which is exactly
        what the open vocabulary exists to prevent.
        """
        if self.fields is not None and self.items is not None:
            raise ValueError(f"feature {self.name!r}: `fields` and `items` are mutually exclusive")
        return self


class CategoricalStats(BaseModel):
    """The vocabulary of a column that has one.

    Present only when the column really is a bounded controlled vocabulary. Absent otherwise, and
    the absence *is* the claim: this column is not a vocabulary.

    It used to be a general cardinality count on every string and numeric column. Counting distinct
    values exactly means *retaining* them, and for a column of prompts the set of distinct values is
    the column. What that bought was a reading of "9,954 distinct in 10,000 rows", which says free
    text, which ``semantic_role`` and the length quantiles already said for free. Nothing read it
    either: the only consumers of the number are a ``<= 2`` test that confirms a binary label and
    the ``<= 32`` gate on ``values`` below.

    The values themselves ARE row content, so they appear only for a column whose detected role makes
    it a controlled vocabulary — the assert-only-what-was-proven rule applied to the one place the
    profiler would otherwise leak the data it is describing.
    """

    distinct_count: int = Field(
        description=(
            "How many distinct values the vocabulary holds. Exact, with no cap to have silently hit: "
            "this model is built only for a column that stayed inside the vocabulary bounds all the "
            "way through, so there is nothing to caveat. A small bounded set corroborates score / "
            "category roles, and `<= 2` is what confirms a binary preference label."
        ),
    )
    values: list[str] | None = Field(
        default=None,
        description=(
            "The observed values, present only when this column's `semantic_role` marks it a controlled "
            "vocabulary (label | provenance | meta | rank) and it holds at most 32 of them. Cardinality "
            "alone cannot be the gate: it inverts on small data, where every column holds few distinct "
            "values — free text included — so a three-row dataset had its prompts stored verbatim. A role "
            "says what a column *is*, at any size. Read `PartitionProfile.rows_complete` to know whether "
            "this is the whole vocabulary or only what the sampled rows showed."
        ),
    )


class ColumnStats(BaseModel):
    """Measurements for one top-level column (keyed by name in ``PartitionProfile.stats``).

    The kind-specific block is populated by dtype; deep measurements fold into it (e.g.
    ``MessageStats.content_chars``) so stats stay flat — no path addressing to drift against the
    schema tree. Never row values — profiles stay safe to display / export without leaking data —
    with one role-gated exception: ``categorical.values``, and only for a column whose role makes it
    a controlled vocabulary rather than free text that happens to repeat.
    """

    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    text: TextStats | None = Field(default=None, description="dtype == string")
    numeric: NumericStats | None = Field(default=None, description="dtype in {int*, uint*, float*}")
    messages: MessageStats | None = Field(default=None, description="dtype == messages (list of {role, content})")
    categorical: CategoricalStats | None = Field(
        default=None,
        description="Present only when the column is a bounded controlled vocabulary; absence means it is not one.",
    )
    quality: TextQuality | None = Field(default=None, description="dtype == string: corruption signals")


class FileError(BaseModel):
    """A file the profiler could not fully use, and why.

    Only failures are enumerated. Healthy files are counted (``SplitProfile.num_files``), because a
    per-file record for each of them scaled the profile with shard count while telling a reader
    nothing: at 512 shards those records were 95% of the payload and every one of them said "this
    file was fine". Problems are the part worth naming, and there are few.
    """

    path: str = Field(description="Relative path within the fileset.")
    error: str = Field(
        description=(
            "Why this file was not fully read: unreadable, corrupt, partially parsed, or in a format "
            "with no reader. A file that was read cleanly never appears here, so the absence of a path "
            "is itself the claim that it was fine."
        ),
    )


class SplitProfile(BaseModel):
    """A split within a partition.

    Resolution precedence (declared structure beats detection):

    1. HF card front-matter when the fileset ships a README — ``configs[].data_files`` maps splits to
       file globs explicitly;
    2. best-effort detection from file paths (train/test/validation markers, sharded layouts like
       ``data/train-00000-of-00003.parquet``); path markers are matched against canonical names and
       common aliases (val/valid/dev -> validation), the normalized concept lands in ``canonical``, and
       the split keeps its on-disk ``name``;
    3. otherwise leave it alone: a single "default" split holding all files.

    A split encoded as a *data column* (a value inside each row rather than a file grouping) is not
    resolved here; such files profile as a single split.
    """

    name: str = Field(description="The on-disk name: train | test | train_prefs | ...")
    canonical: str | None = Field(
        default=None,
        description=(
            "Normalized concept: train | validation | test; None when nothing matches. E.g. train_prefs -> "
            "train, with the variant's intent kept in `name`."
        ),
    )
    data_files: str | None = Field(
        default=None,
        description=(
            "A glob selecting exactly this split's files, relative to the fileset root: \"helpsteer2/"
            'train*.parquet". Gives the files back their addressability without giving back the '
            "per-file manifest — one pattern per split, whatever the shard count — so a consumer can "
            "hand a reader the files of one split without listing the fileset and re-deriving which "
            "shards belong where. Named for HF card front-matter's `configs[].data_files`, which is "
            "the declared form of this same claim and, once cards are parsed, the thing that will "
            "replace this inference rather than sit beside it in a second vocabulary.\n\n"
            "`*` spans any run of characters except `/` — the one reading shared by shell globs, "
            "Python's glob, fsspec and HF — so the pattern means the same thing wherever it is pasted. "
            "`**` is never emitted, because its meaning is not shared.\n\n"
            "None when no single pattern selects these files and nothing else (shards spread across "
            "subdirectories, say). Never approximate: a pattern is emitted only after being matched "
            "back against every file in the fileset and found to select this split exactly. A glob is "
            "an instruction to go read files, so a near miss is not a rougher answer — it silently "
            "pulls a README, or a neighbouring split's shards, into a training set."
        ),
    )
    num_files: int = Field(
        default=0,
        description=(
            "How many files resolved into this split. Partitioning is exhaustive and disjoint — each file "
            "of the partition lands in exactly one split — so these sum to the partition's file count. "
            "A count rather than a list: the paths of healthy shards are the one part of a profile that "
            "grows without bound and informs no decision."
        ),
    )
    size_bytes: int = Field(
        default=0,
        description=(
            "On-disk bytes of this split's files, summed. Answers whether the data fits wherever the "
            "reader means to put it — the first question asked of an unfamiliar dataset, and one a row "
            "count cannot answer, since a row ranges from an integer score to a reasoning trace. "
            "Unlike `num_examples` this is never None: it comes from the file listing rather than from "
            "reading, so a file that failed mid-read still contributes its size. Bytes as stored — "
            "compressed, and several times this once decoded into memory. Covers only files a "
            "partition grouped; a format with no reader never reaches a split, so weigh the whole "
            "fileset with `SamplingInfo.bytes_present`."
        ),
    )
    num_examples: int | None = Field(
        default=None,
        description=(
            "Rows in this split, counting every one of its files whether or not that file's rows were "
            "read. Always "
            "exact — summed from parquet footers or from files read to their end — and None the moment any "
            "one file's count is unknown. Never an estimate, so it carries no accuracy caveat: a capped run "
            "still reports the true total whenever the footers knew it."
        ),
    )


class PartitionProfile(BaseModel):
    """A file-group sharing one row schema and one source directory (roughly an HF config).

    File membership and row counts live on ``splits`` — every file lands in exactly one split, so
    partition-level files / num_examples would be derivable duplication.
    """

    name: str = Field(
        default="",
        description=(
            "Identifies this partition, and unique within a profile. It is the path prefix its files "
            'share within the fileset: a top-level directory, or "" when they sit at the fileset '
            "root. Empty is a safe sentinel precisely because no directory can be named it, so "
            "root-level files stay distinct from a directory literally called 'default'. Once card "
            "front-matter is parsed, a declared config name populates this field instead — the same "
            'claim from a better source. For display, read it as `name or "default"`: storing that '
            "default was a lossy habit, because a lone partition under `data/` then reported "
            '"default" and threw away the only thing identifying it.'
        ),
    )
    file_formats: list[str] = Field(
        default_factory=list,
        description=(
            "The distinct formats this partition's files are in, sorted — normally exactly one, and "
            "more than one when a stray .jsonl sits beside .parquet shards. That is noise, not a "
            "second dataset, so it stays in this partition and shows up here rather than splitting it. "
            "jsonl | parquet are read today; csv | arrow are reserved vocabulary the profiler cannot "
            "read yet and reports on `DatasetProfile.file_errors` instead."
        ),
    )
    splits: list[SplitProfile] = Field(description="card-declared > path-detected > single 'default' split.")
    features: list[FeatureSchema] = Field(
        description="The row schema: measured layout plus detected role markers, derived de novo (nested).",
    )
    stats: dict[str, ColumnStats] = Field(
        default_factory=dict,
        description=(
            "Top-level column name -> measurements; sparse (a column with nothing worth measuring is "
            "omitted); keys are a subset of the top-level `features` names."
        ),
    )
    rows_complete: bool = Field(
        description=(
            "True => every row of every file in THIS partition was read. Only then can a consumer "
            "assert enum / required in a bridged JSON Schema, or read a verifiability coverage of "
            "1.0 as literal.\n\n"
            "Named for what it measures. It was `stats_complete`, which promised more than it "
            "delivered: `Quantiles` and `TextQuality` are estimates by construction however much was "
            "read, each bounded for the cost reasons its own docstring gives. Whether a number is "
            "exact is a property of that number, and every one of them says so; this says only "
            "whether anything was missed on the way in.\n\n"
            "Scoped to the partition because that is where it is decided — a corrupt shard in one "
            "partition says nothing about the measurements in another, and a fileset-wide flag "
            "quietly downgraded every partition to the worst one."
        ),
    )
    classification: PartitionClassification

    @model_validator(mode="after")
    def _stats_keys_subset_of_features(self) -> PartitionProfile:
        """``stats`` is keyed by top-level column name, so every key must name a top-level feature
        (the producer keys stats by ``feature.name``); a stray key is a malformed profile."""
        unknown = set(self.stats) - {feature.name for feature in self.features}
        if unknown:
            raise ValueError(f"stats keys must name top-level features; unknown columns: {sorted(unknown)}")
        return self


# ---- envelope ----------------------------------------------------------------------------------


class SamplingInfo(BaseModel):
    """How much of the data the profile is based on — coverage, stated as numbers.

    Deliberately carries no ``exhaustive`` flag. That bit was answering two questions at once: "are
    these measurements facts or estimates?", which is a property of each measurement and is now
    stated by each of them, and "did I see all the data?", which is this block's job and needs
    numerators and denominators rather than a boolean. It also folded together causes that call for
    different people to act — a short read is the caller's choice, a corrupt shard is the data
    owner's problem, and a missing reader is ours.

    Nor does it record the caller's row limit. Reading everything is now the default and costs what
    reading some of it costs, so a short read is unusual — and when it happens ``rows_scanned``
    against ``rows_present`` already says so. *Why* is not the profile's business: a limit is an
    input, and the only other cause is a file that failed, which is named on ``file_errors``.

    The dataset-wide question is still one expression away, and still says which half failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    rows_scanned: int = Field(description="Total rows actually parsed across all files.")
    rows_present: int | None = Field(
        default=None,
        description=(
            "How many rows the fileset holds, scanned or not — the denominator `rows_scanned` is a "
            "fraction of. Populated whenever every file's count is *known*, regardless of how much was "
            "read: a row-capped run over parquet still knows its totals from the footers, and that is "
            "exactly when the ratio carries information. None means at least one file's count is "
            "unknown — never zero, never an estimate."
        ),
    )
    files_read: int = Field(
        description=(
            "Files actually opened and read from. A count, not a list -- the paths of healthy "
            "shards are the one part of a profile that grows without bound and informs no "
            "decision; `SplitProfile.num_files` counts them per split, and only the ones that "
            "went wrong are named, on `DatasetProfile.file_errors`."
        )
    )
    files_present: int = Field(
        description=(
            "Data files the fileset holds, whether or not this run could read them — the denominator "
            "`files_read` is a fraction of. Includes files in formats with no reader, since those are "
            "data that went unprofiled (they are named on `DatasetProfile.file_errors`). A README "
            "is not data and is counted nowhere. Every readable file should be opened, since "
            "head-sampling a *subset of files* hides columns that appear only in later shards, so expect "
            "these two to match until scale forces file-level sampling."
        ),
    )
    bytes_present: int = Field(
        default=0,
        description=(
            "On-disk bytes of every data file the fileset holds, whether or not this run could read it "
            "— the size of the dataset as it sits, independent of how much was profiled. Redundant "
            "with the sum over `SplitProfile.size_bytes` exactly when nothing failed, and load-bearing "
            "when something did: a file in a format with no reader never reaches a partition, so a "
            "directory of .csv shards beside one .parquet would otherwise weigh in at the parquet "
            "alone. Same reason `files_present` is kept alongside the per-split counts — a denominator "
            "stops being derivable the moment coverage is partial, which is the only time it is read."
        ),
    )


class DatasetProfile(BaseModel):
    """The machine-owned dataset profile — the root of the stored contract.

    Deliberately carries no staleness marker, and no per-file manifest to reconstruct one from. A
    stored digest would freeze "which files count as inputs" into the data at write time, and that
    judgment moves: once card front-matter drives split declaration, ``README.md`` becomes an input.
    Changing the rule would then invalidate every stored profile at once, with no way to tell a real
    change from a definition change.

    So a profile says when it was made and nothing about whether it still holds. ``created_at`` is
    the whole of it. That is deliberate while profiling is user-triggered and nothing consumes
    freshness; when something does, the cheap primitive is a fileset version token from the storage
    backend, which costs no listing and freezes no policy — not a manifest reconstructed here.
    """

    profile_schema_version: str = Field(
        default=PROFILE_SCHEMA_VERSION,
        description='Semver of THIS contract (e.g. "1.0") — gates consumer compatibility.',
    )
    created_at: datetime
    profiler_info: dict = Field(
        default_factory=dict,
        description="Free-form profiler metadata (name, version, git sha, timings).",
    )
    sampling: SamplingInfo = Field(description="How much data the profile is based on.")
    partitions: list[PartitionProfile] = Field(
        description="Single partition in the common homogeneous case; there is no fileset-level rollup.",
    )
    file_errors: list[FileError] = Field(
        default_factory=list,
        description=(
            "Every file the profiler could not fully use, from anywhere in the fileset: a format with "
            "no reader, a corrupt shard, a partially parsed one. Reporting them is what keeps a "
            "directory of .csv shards from profiling as an exhaustively scanned *empty* dataset, "
            "indistinguishable from one that really is empty. One list rather than two, because "
            '"a file I could not use" is the same finding whether or not a partition managed to group '
            'it first, and a reader asking "did anything go wrong?" should not have to look twice.'
        ),
    )


# Resolve the recursive FeatureSchema self-reference (deferred by `from __future__ import annotations`).
FeatureSchema.model_rebuild()
