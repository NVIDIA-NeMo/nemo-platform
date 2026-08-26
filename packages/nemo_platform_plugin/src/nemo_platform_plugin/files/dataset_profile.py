# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The stored contract for the dataset profiler.

A ``DatasetProfile`` is machine-owned metadata the profiler computes once, at the Files layer, so
every consumer reads one typed description of a dataset instead of downloading and re-inspecting it.
It has two stored layers:

* **structure** -- predominantly facts: file layout, splits, the derived row schema (``features``)
  and per-column ``stats``. The one detected attribute here is ``FeatureSchema.semantic_role``.
* **classification** -- what the data *is*: ``dataset_type``, the ``format`` / ``prompt_form`` axes,
  and ``verifiability``.

Vocabularies (``dataset_type``, ``semantic_role``, ``modality``, ...) are open ``str`` values with
documented canonical sets, not closed enums: only known values are emitted, but consumers must
tolerate unknown ones so the vocabulary can grow without a breaking change. Pydantic's default
``extra="ignore"`` gives the same forward-compatibility for unknown *fields*.

It lives in a shared package rather than with the profiler because the Files service stores and
serves a profile as its own entity, so a deployment that installs no profiler still needs the type
to deserialize its own rows. The module is pydantic-only: the profiler imports it standalone, and
Files imports it as the type it persists. A profile is a separate entity from fileset metadata, so
writing one cannot clobber an unrelated metadata edit."""

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
            "Every dataset type the assigned roles satisfy, most specific first, so `candidates[0]` is "
            "`dataset_type`. The tail is structures the same columns also satisfy: prompt + completion + score + "
            "label is genuinely both `scored_response` and `unpaired_preference`, and a consumer that cares picks "
            "by its own rule rather than by ours."
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
    apart from "mostly short with a long tail", and those call for opposite sequence budgets.

    **p50 / p95 / p99 are estimates, within a couple of percent**, read off counters bucketed by
    magnitude rather than off the lengths themselves. Every row is counted, so the *rank* is exact;
    only the value is rounded.

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
            'The distinct role strings present in the sampled rows, verbatim -- e.g. ["system", "user", '
            '"assistant", "tool"], but equally ["human", "gpt"]. A measurement of row content, not a closed '
            "vocabulary: an unexpected role is the finding worth reporting, and normalizing it away would hide "
            "what a consumer needs before choosing a chat template. Bounded, since a column with more distinct "
            "roles than fit here is not a chat column."
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


class FeatureSchema(BaseModel):
    """One node of the row schema, derived from the data rather than referenced from a schema store.
    Carries the measured layout (name, dtype, children) plus at most one detected ``semantic_role``.

    Recursive and fully expanded: a ``struct`` node has child ``fields``, and a ``list`` /
    ``messages`` node has an element ``items``. For ``messages`` the per-message ``{role, content}``
    struct is spelled out, so a vision message whose content is a list of typed parts shows up
    structurally. The column-level chat summary lives in ``MessageStats``. This tree is the
    bridgeable schema artifact -- to a JSON Schema, or a UI columns view.
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
            "Where `semantic_role` came from: detected | declared. A declared role was asserted by the caller and "
            "still had to pass the dtype gate; a detected one came from the column name. Stored so a consumer can "
            "weigh the two differently."
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

    Present only when the column really is a bounded controlled vocabulary. Absent otherwise, and the
    absence *is* the claim: this column is not a vocabulary.

    Not a general cardinality count -- counting distinct values exactly means *retaining* them, and
    for a column of prompts the distinct set is the column. The number has two consumers: a ``<= 2``
    test confirming a binary label, and the ``<= 32`` gate on ``values``.
    """

    distinct_count: int = Field(
        description=(
            "How many distinct values the vocabulary holds. Exact, and present only for a column that stayed a "
            "bounded vocabulary throughout -- absence means the column is not one, not that counting was skipped."
        ),
    )
    values: list[str] | None = Field(
        default=None,
        description=(
            "The observed values, present only when this column's `semantic_role` makes it a controlled "
            "vocabulary and the count is small enough to quote. This is the one place row content reaches the "
            "stored profile, so it is gated on role rather than on size: cardinality inverts on small data, where "
            "every column looks like an enumeration."
        ),
    )


class ColumnStats(BaseModel):
    """Measurements for one top-level column (keyed by name in ``PartitionProfile.stats``).

    The kind-specific block is populated by dtype, and deep measurements fold into it (e.g.
    ``MessageStats.content_chars``) so stats stay flat -- no path addressing to drift against the
    schema tree. Never row values, with one role-gated exception: ``categorical.values``.
    """

    null_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    text: TextStats | None = Field(default=None, description="dtype == string")
    numeric: NumericStats | None = Field(default=None, description="dtype in {int*, uint*, float*}")
    messages: MessageStats | None = Field(default=None, description="dtype == messages (list of {role, content})")
    categorical: CategoricalStats | None = Field(
        default=None,
        description="Present only when the column is a bounded controlled vocabulary; absence means it is not one.",
    )


class FileError(BaseModel):
    """A file the profiler could not fully use, and why.

    Only failures are enumerated. Healthy files are counted (``SplitProfile.num_files``), because a
    per-file record for each scaled the profile with shard count while telling a reader nothing: at
    512 shards those records were 95% of the payload.
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

    Resolution precedence, declared structure beating detection:

    1. HF card front-matter when the fileset ships a README -- ``configs[].data_files`` maps splits
       to file globs explicitly;
    2. detection from file paths (train/test/validation markers, sharded layouts). Markers are
       matched against canonical names and common aliases (val/valid/dev -> validation); the
       normalized concept lands in ``canonical`` and the split keeps its on-disk ``name``;
    3. otherwise a single "default" split holding all files.

    A split encoded as a *data column* rather than a file grouping is not resolved here.
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
            "A glob selecting exactly this split's files, relative to the fileset root: "
            '"helpsteer2/train*.parquet". One pattern per split whatever the shard count, so a consumer can read '
            "one split without listing the fileset and re-deriving which shards belong where. Named for HF card "
            "front-matter's `configs[].data_files`.\n\n"
            "`*` spans any run of characters except `/` -- the reading shared by shell globs, Python's glob, "
            "fsspec and HF. `**` is never emitted, because its meaning is not shared.\n\n"
            "None when no single pattern selects these files and nothing else. Never approximate: a pattern is "
            "emitted only after being matched against every file in the fileset and found to select this split "
            "exactly, since a near miss would silently pull in a README or a neighbouring split's shards."
        ),
    )
    num_files: int = Field(
        default=0,
        description=(
            "How many files resolved into this split. Partitioning is exhaustive over the partition's data files, "
            "so these sum to the partition's total."
        ),
    )
    size_bytes: int = Field(
        default=0,
        description=(
            "On-disk bytes of this split's files, summed. Answers whether the data fits wherever the reader means "
            "to put it, which a row count cannot: a row ranges from an integer score to a reasoning trace. Never "
            "None, since it comes from the file listing rather than from reading. Bytes as stored -- compressed, "
            "and several times this once decoded."
        ),
    )
    num_examples: int | None = Field(
        default=None,
        description=(
            "Rows in this split, counting every one of its files whether or not that file was read to the end. "
            "None when any file's count is unknown, which is the honest answer: the sum of the rest would look "
            "like a fact and read low."
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
            "Identifies this partition, and unique within a profile. The path prefix its files share within the "
            'fileset: a top-level directory, or "" when they sit at the fileset root. Empty is a safe sentinel '
            "because no directory can be named it. Once card front-matter is parsed, a declared config name "
            'populates this instead. For display, read it as `name or "default"` rather than storing that '
            "default, which would throw away the only thing identifying the partition."
        ),
    )
    file_formats: list[str] = Field(
        default_factory=list,
        description=(
            "The distinct formats this partition's files are in, sorted -- normally one. Observed rather than "
            "chosen: a directory holding two formats has a stray file, not a second dataset, and splitting the "
            "partition to keep a single value true made partition names unstable."
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
            "True => every row of every file in THIS partition was read. Only then can a consumer assert enum / "
            "required in a bridged JSON Schema, or read a verifiability coverage of 1.0 as literal.\n\n"
            "It says whether anything was missed on the way in, not whether a given number is exact -- that is a "
            "property of the number, and each one says so. Scoped to the partition, because a corrupt shard in "
            "one says nothing about the measurements in another."
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


class Coverage(BaseModel):
    """How much of the data the profile is based on, stated as numbers rather than as a verdict.

    It carries no ``exhaustive`` flag. That bit answered two questions at once -- whether a given
    measurement is a fact or an estimate, which each measurement now states for itself, and whether
    all the data was seen, which needs numerators and denominators. It also folded together causes
    that call for different people to act: a short read is the caller's choice, a corrupt shard is
    the data owner's problem, a missing reader is ours.

    The dataset-wide question is one expression away, and still says which half failed::

        all(p.rows_complete for p in profile.partitions) and not profile.file_errors
    """

    rows_scanned: int = Field(description="Total rows actually parsed across all files.")
    rows_present: int | None = Field(
        default=None,
        description=(
            "How many rows the fileset holds, scanned or not -- the denominator `rows_scanned` is a fraction of. "
            "None once any file's count is unknown, since a total that omits it would read low as though it were "
            "a fact."
        ),
    )
    files_read: int = Field(
        description=(
            "Files actually opened and read from. A count, not a list: the paths worth naming are the ones that "
            "failed, and those are on `file_errors`."
        )
    )
    files_present: int = Field(
        description=(
            "Data files the fileset holds, whether or not this run could read them -- the denominator "
            "`files_read` is a fraction of. Counts files in formats with no reader too, since those are data the "
            "profile does not describe. Non-data files (a README, a LICENSE) are counted nowhere."
        ),
    )
    bytes_present: int = Field(
        default=0,
        description=(
            "On-disk bytes of every data file the fileset holds, whether or not this run could read it -- the "
            "size of the dataset as it sits, independent of how much was profiled. Equal to the sum over "
            "`SplitProfile.size_bytes` when nothing failed, and load-bearing when something did: a file in a "
            "format with no reader never reaches a partition."
        ),
    )


class DatasetProfile(BaseModel):
    """The machine-owned dataset profile -- the root of the stored contract.

    It carries no staleness marker, and no per-file manifest to reconstruct one from. A stored digest
    would freeze "which files count as inputs" into the data at write time, and that judgment moves:
    once card front-matter drives split declaration, ``README.md`` becomes an input, and changing the
    rule would invalidate every stored profile at once.

    So a profile says when it was made and nothing about whether it still holds. When something does
    consume freshness, the cheap primitive is a fileset version token from the storage backend.
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
    coverage: Coverage = Field(description="How much data the profile is based on.")
    partitions: list[PartitionProfile] = Field(
        description="Single partition in the common homogeneous case; there is no fileset-level rollup.",
    )
    file_errors: list[FileError] = Field(
        default_factory=list,
        description=(
            "Every file the profiler could not fully use, from anywhere in the fileset, sorted by path. Files "
            "that read cleanly are counted rather than listed, so this is a findings list and not a manifest. A "
            "non-empty list is what makes `rows_present` unknown."
        ),
    )


# Resolve the recursive FeatureSchema self-reference (deferred by `from __future__ import annotations`).
FeatureSchema.model_rebuild()
