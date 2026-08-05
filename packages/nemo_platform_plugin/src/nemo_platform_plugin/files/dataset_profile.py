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

This module is pydantic-only — no platform dependencies — so the profiler can import it as a
standalone contract and ``DatasetMetadataContent`` can later carry it as a typed field.
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
    """A per-row distribution summary. p99 = long-tail sequence-length signal; max = hard cap."""

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
            "would hide exactly what a consumer needs to see before choosing a chat template."
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
    """Cheap, single-pass corruption signals for a text column. Flags training-wrecking data, not
    toxicity / PII.
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
    fixed_length: int | None = Field(
        default=None,
        description=(
            "dtype == list: constant observed element count (e.g. an embedding vector's 768), None when "
            "variable. Multi-dimensional shapes compose via nesting."
        ),
    )
    fields: list[FeatureSchema] | None = Field(default=None, description="dtype == struct: named child fields.")
    items: FeatureSchema | None = Field(default=None, description="dtype in {list, messages}: element schema.")

    @model_validator(mode="after")
    def _fields_and_items_are_exclusive(self) -> FeatureSchema:
        """A node is either a named-field container or has a single element schema, never both.

        Deliberately the only structural check here: it holds for *any* dtype, so it costs no
        forward compatibility. Tying `fields` / `items` / `fixed_length` to specific dtype values
        would instead reject a profile written by a newer profiler that added a container dtype,
        which is exactly what the open vocabulary exists to prevent.
        """
        if self.fields is not None and self.items is not None:
            raise ValueError(f"feature {self.name!r}: `fields` and `items` are mutually exclusive")
        return self


class CategoricalStats(BaseModel):
    """Cardinality signals for string / int columns.

    ``distinct_count`` is a count, not row content, and is always safe to store. The values
    themselves ARE row content, so they appear only for a column whose detected role makes it a
    controlled vocabulary — the assert-only-what-was-proven rule applied to the one place the
    profiler would otherwise leak the data it is describing.
    """

    distinct_count: int = Field(
        description=(
            "Distinct values among scanned rows: ~=rows_scanned -> id-like; a small bounded set "
            "corroborates score / category roles."
        ),
    )
    values: list[str] | None = Field(
        default=None,
        description=(
            "The observed values, present only when this column's `semantic_role` marks it a controlled "
            "vocabulary (label | provenance | meta | rank) and it holds at most 32 of them. Cardinality "
            "alone cannot be the gate: it inverts on small data, where every column holds few distinct "
            "values — free text included — so a three-row dataset had its prompts stored verbatim. A role "
            "says what a column *is*, at any size. Read `PartitionProfile.stats_complete` to know whether "
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
    categorical: CategoricalStats | None = Field(default=None, description="low observed cardinality only")
    quality: TextQuality | None = Field(default=None, description="dtype == string: corruption signals")


class FileRecord(BaseModel):
    """One physical file, measured.

    Stores the file's identity as the listing reported it — path, size, checksum — plus what the
    reader learned cheaply. Concatenating ``files`` across a partition's splits reproduces that
    partition's input list exactly, which is what lets a consumer compare a stored profile against a
    fresh listing to see what changed.
    """

    path: str = Field(description="Relative path within the fileset.")
    size_bytes: int
    checksum: str | None = Field(
        default=None,
        description=(
            'As the Files service reports it (e.g. "sha256:..."), when it reports one at all — no backend '
            "does today. Without it, (path, size) is all there is to compare against a fresh listing: enough "
            "to catch files added, removed, renamed or resized, but not a same-size in-place edit."
        ),
    )
    file_format: str | None = Field(
        default=None,
        description=(
            "The format this file was read as (jsonl | parquet). A property of the file, not of the "
            "partition holding it — which is why a partition may hold more than one. None only on a "
            "profile written before formats were recorded per file."
        ),
    )
    read_strategy: str | None = Field(
        default=None,
        description=(
            "How this file's rows were sampled: full | head. The *policy* applied, not the outcome — "
            "a head-capped read of a file smaller than the cap still says head, and whether it ended "
            "up complete is `num_rows` versus what was scanned. Per file because it follows format, "
            "which is also per file: a parquet shard can be sampled by row group where a jsonl file "
            "in the same partition can only be read from the top."
        ),
    )
    num_rows: int | None = Field(
        default=None,
        description="Exact only (parquet footer / exhaustive scan), else None.",
    )
    error: str | None = Field(
        default=None,
        description=(
            "Why this file was not fully read, when it wasn't — unreadable, corrupt, or partially "
            "parsed. None means a clean read. Without it a missing `num_rows` is indistinguishable "
            "from a profiler bug, and a consumer cannot tell corrupt input from unsupported input."
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
    files: list[FileRecord] = Field(
        description=(
            "Every file resolved into this split, measured. Partitioning is exhaustive and disjoint: each "
            "file of the partition lands in exactly one split, so concatenating `files` across splits "
            "reconstructs the partition's file list with no gaps or repeats."
        ),
    )
    num_examples: int | None = Field(
        default=None,
        description=(
            "Rows in this split, counting every file in `files` whether or not its rows were read. Always "
            "exact — summed from parquet footers or from files read to their end — and None the moment any "
            "one file's count is unknown. Never an estimate, so it carries no accuracy caveat: a capped run "
            "still reports the true total whenever the footers knew it."
        ),
    )


class PartitionProfile(BaseModel):
    """A file-group sharing one row schema and one source directory (roughly an HF config).

    File membership and row counts live on ``splits`` — every file lands in exactly one split, so
    partition-level files / num_examples would be derivable duplication.

    ``source_dir`` is the identity and ``name`` is a label. They were a single string until the
    consequences showed: root-level files and a directory literally named ``default`` collided under
    one label, and dropping an unrelated file into a directory renamed that partition out of
    existence — not changed, *gone*, so a stored reference resolved to nothing.
    """

    name: str = Field(
        default="default",
        description=(
            "Display label, NOT a key. Derived from the layout, not guaranteed unique, and free to "
            "change when the layout does. Reference a partition by `source_dir` — or, once card "
            "front-matter is parsed, by its declared config name."
        ),
    )
    source_dir: str | None = Field(
        default=None,
        description=(
            "Top-level directory whose files make up this partition; None when they sit at the "
            "fileset root. The partition's identity: None and a directory named 'default' are "
            'different partitions even though both label as "default".'
        ),
    )
    file_formats: list[str] = Field(
        default_factory=list,
        description=(
            "The distinct formats among this partition's files, sorted — normally exactly one. "
            "Format is a property of a file (see `FileRecord.file_format`), never a partition "
            "dimension: a stray .jsonl beside .parquet shards is noise, not a second dataset, so it "
            "stays in this partition and shows up here. jsonl | parquet are read today; csv | arrow "
            "are reserved vocabulary the profiler cannot read yet and reports as unsupported."
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
    stats_complete: bool = Field(
        description=(
            "True => `features`, `stats` and `classification` were computed over every row of every "
            "file in THIS partition: proven facts, not estimates. Only then can a consumer assert "
            "enum / required in a bridged JSON Schema, or read a verifiability coverage of 1.0 as "
            "literal. Scoped to the partition because that is where it is decided — a corrupt shard "
            "in one partition says nothing about the measurements in another, and a fileset-wide "
            "flag quietly downgraded every partition to the worst one."
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

    @model_validator(mode="after")
    def _file_formats_cover_the_records(self) -> PartitionProfile:
        """Every format recorded on a file must appear in the partition's summary.

        A subset check rather than equality, so the two cannot drift in the direction that matters:
        a summary omitting a format that demonstrably exists is wrong, while a profile written
        before formats were recorded per file has nothing on its records and nothing to check.
        """
        recorded = {file.file_format for split in self.splits for file in split.files if file.file_format}
        missing = recorded - set(self.file_formats)
        if missing:
            raise ValueError(f"file_formats omits formats present on this partition's files: {sorted(missing)}")
        return self


# ---- envelope ----------------------------------------------------------------------------------


class SamplingInfo(BaseModel):
    """How much of the data the profile is based on — coverage, stated as numbers.

    Deliberately carries no ``exhaustive`` flag. That bit was answering two questions at once: "are
    these measurements facts or estimates?", which is a property of a *partition* and now lives on
    ``PartitionProfile.stats_complete``, and "did I see all the data?", which is this block's job and
    needs numerators and denominators rather than a boolean. It also folded together causes that
    call for different people to act — a row cap is the caller's choice, a corrupt shard is the data
    owner's problem, and a missing reader is ours.

    The dataset-wide question is still one expression away, and now says which half failed::

        all(p.stats_complete for p in profile.partitions) and not profile.unreadable_files
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
        description="Files actually opened and read from (a count; the files themselves are `SplitProfile.files`)."
    )
    files_present: int = Field(
        description=(
            "Data files the fileset holds, whether or not this run could read them — the denominator "
            "`files_read` is a fraction of. Includes files in formats with no reader, since those are "
            "data that went unprofiled (they are listed in `DatasetProfile.unreadable_files`). A README "
            "is not data and is counted nowhere. Every readable file should be opened, since "
            "head-sampling a *subset of files* hides columns that appear only in later shards, so expect "
            "these two to match until scale forces file-level sampling."
        ),
    )
    per_file_row_cap: int | None = Field(default=None, description="Cap that bounded per-file reads, if any.")
    seed: int | None = Field(default=None, description="RNG seed used for row selection, for reproducibility.")


class DatasetProfile(BaseModel):
    """The machine-owned dataset profile — the root of the stored contract.

    Deliberately carries no staleness marker. A stored digest would freeze "which files count as
    inputs" into the data at write time, and that judgment moves: once card front-matter drives
    split declaration, ``README.md`` becomes an input. Changing the rule would then invalidate every
    stored profile at once, with no way to tell a real change from a definition change. The
    ``FileRecord``s already describe the inputs, so a consumer that needs to know whether a profile
    is current compares them against a fresh listing — same cost, and it learns *what* changed
    rather than merely *that* something did.
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
    unreadable_files: list[FileRecord] = Field(
        default_factory=list,
        description=(
            "Files that plainly hold dataset records but that no partition could take, because the "
            "profiler has no reader for their format; each carries the reason on `error`. Reporting "
            "them is what keeps a directory of .csv shards from profiling as an exhaustively scanned "
            "*empty* dataset, indistinguishable from one that really is empty. A file whose format is "
            "known but whose read failed keeps its FileRecord inside its split instead — it was "
            "grouped and attempted, these never were."
        ),
    )


# Resolve the recursive FeatureSchema self-reference (deferred by `from __future__ import annotations`).
FeatureSchema.model_rebuild()
