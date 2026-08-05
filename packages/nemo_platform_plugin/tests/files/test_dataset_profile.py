# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the dataset-profiler stored contract.

Three representative datasets — a conversational prompt/completion set, a conversational preference
pair, and a standard scored-response set — are embedded as YAML fixtures and exercised as executable
expectations: if a field name, alias, or vocabulary value drifts, one of these deserializations
breaks.
"""

from datetime import datetime

import pytest
import yaml
from nemo_platform_plugin.files.dataset_profile import (
    PROFILE_SCHEMA_VERSION,
    ColumnStats,
    DatasetProfile,
    Evidence,
    FeatureSchema,
    FileRecord,
    MessageStats,
    PartitionClassification,
    PartitionProfile,
    Quantiles,
    SamplingInfo,
    SplitProfile,
    Verifiability,
)
from pydantic import ValidationError

# --- Fixture: trl-lib/OpenMathReasoning (conversational prompt_completion, verifiable) ---
OPENMATHREASONING = """
profile_schema_version: "1.0"
created_at: 2026-07-08T22:05:12Z
profiler_info: {name: nemo-dataset-profiler, version: 0.1.0}
sampling: {rows_scanned: 2112, rows_present: 3201061,
           files_read: 33, files_present: 33, per_file_row_cap: 64}
partitions:
  - name: default
    source_dir: null
    file_formats: [parquet]
    stats_complete: false
    splits:
      - {name: train, canonical: train, num_examples: 3200861,
         files: [{path: train-00000-of-00032.parquet, size_bytes: 193777041,
                  checksum: sha256:9c1e..., num_rows: 100027, file_format: parquet, read_strategy: head}]}
      - {name: test, canonical: test, num_examples: 200,
         files: [{path: test-00000-of-00001.parquet, size_bytes: 411552,
                  checksum: sha256:02af..., num_rows: 200, file_format: parquet, read_strategy: head}]}
    features:
      - {name: prompt, dtype: messages, semantic_role: prompt,
         items: {dtype: struct, fields: [{name: role, dtype: string}, {name: content, dtype: string}]}}
      - {name: completion, dtype: messages, semantic_role: completion,
         items: {dtype: struct, fields: [{name: role, dtype: string}, {name: content, dtype: string}]}}
    stats:
      prompt:     {messages: {turns: {p50: 1, p95: 1, p99: 1, max: 1}, content_chars: {p50: 180, p95: 620, p99: 1100, max: 4800},
                              roles_seen: [user], ends_with_assistant_rate: 0.0, valid_alternation_rate: 1.0}}
      completion: {messages: {turns: {p50: 1, p95: 1, p99: 1, max: 1}, content_chars: {p50: 2400, p95: 7800, p99: 12000, max: 32000},
                              roles_seen: [assistant], ends_with_assistant_rate: 1.0, valid_alternation_rate: 1.0}}
    classification:
      modality: text
      dataset_type: prompt_completion
      format: conversational
      prompt_form: explicit
      verifiability:
        method: extractable_final_answer
        coverage: 0.81
        evidence: [{kind: content_probe, detail: 'completion ends with \\boxed{...} in 81% of 2112 sampled rows'}]
      evidence:
        - {kind: column_name,   detail: "prompt + completion column pair"}
        - {kind: content_probe, detail: "prompt ends on a user turn, completion is a single assistant turn"}
"""

# --- Fixture: trl-lib/hh-rlhf-helpful-base (conversational preference_pair, explicit) -----
HH_RLHF_HELPFUL_BASE = """
profile_schema_version: "1.0"
created_at: 2026-07-08T22:41:37Z
profiler_info: {name: nemo-dataset-profiler, version: 0.1.0}
sampling: {rows_scanned: 1024, rows_present: 46189,
           files_read: 2, files_present: 2, per_file_row_cap: 512}
partitions:
  - name: default
    source_dir: null
    file_formats: [parquet]
    stats_complete: false
    splits:
      - {name: train, canonical: train, num_examples: 43835,
         files: [{path: train-00000-of-00001.parquet, size_bytes: 22105331,
                  checksum: sha256:77b0..., num_rows: 43835, file_format: parquet, read_strategy: head}]}
      - {name: test, canonical: test, num_examples: 2354,
         files: [{path: test-00000-of-00001.parquet, size_bytes: 1198422,
                  checksum: sha256:5c1d..., num_rows: 2354, file_format: parquet, read_strategy: head}]}
    features:
      - {name: prompt, dtype: messages, semantic_role: prompt,
         items: {dtype: struct, fields: [{name: role, dtype: string}, {name: content, dtype: string}]}}
      - {name: chosen, dtype: messages, semantic_role: chosen,
         items: {dtype: struct, fields: [{name: role, dtype: string}, {name: content, dtype: string}]}}
      - {name: rejected, dtype: messages, semantic_role: rejected,
         items: {dtype: struct, fields: [{name: role, dtype: string}, {name: content, dtype: string}]}}
    stats:
      prompt:   {messages: {turns: {p50: 3, p95: 8, p99: 9, max: 9}, content_chars: {p50: 640, p95: 3200, p99: 5400, max: 9800},
                            roles_seen: [user, assistant], ends_with_assistant_rate: 0.0, valid_alternation_rate: 1.0}}
      chosen:   {messages: {turns: {p50: 1, p95: 1, p99: 1, max: 1}, content_chars: {p50: 420, p95: 1400, p99: 2100, max: 3600},
                            roles_seen: [assistant], ends_with_assistant_rate: 1.0, valid_alternation_rate: 1.0}}
      rejected: {messages: {turns: {p50: 1, p95: 1, p99: 1, max: 1}, content_chars: {p50: 410, p95: 1380, p99: 2050, max: 3500},
                            roles_seen: [assistant], ends_with_assistant_rate: 1.0, valid_alternation_rate: 1.0}}
    classification:
      modality: text
      dataset_type: preference_pair
      format: conversational
      prompt_form: explicit
      evidence:
        - {kind: column_name,   detail: "chosen + rejected column pair"}
        - {kind: content_probe, detail: "prompt carries the multi-turn history ending on a user turn"}
"""

# --- Fixture: nvidia/HelpSteer2 (standard scored_response, no verifiability) --------------
HELPSTEER2 = """
profile_schema_version: "1.0"
created_at: 2026-07-09T10:12:45Z
profiler_info: {name: nemo-dataset-profiler, version: 0.1.0}
sampling: {rows_scanned: 1024, rows_present: 21362,
           files_read: 2, files_present: 2, per_file_row_cap: 512}
partitions:
  - name: default
    source_dir: null
    file_formats: [parquet]
    stats_complete: false
    splits:
      - {name: train, canonical: train, num_examples: 20324,
         files: [{path: train-00000-of-00001.parquet, size_bytes: 44201991,
                  checksum: sha256:e410..., num_rows: 20324, file_format: parquet, read_strategy: head}]}
      - {name: validation, canonical: validation, num_examples: 1038,
         files: [{path: validation-00000-of-00001.parquet, size_bytes: 2311008,
                  checksum: sha256:8bd2..., num_rows: 1038, file_format: parquet, read_strategy: head}]}
    features:
      - {name: prompt,      dtype: string, semantic_role: prompt}
      - {name: response,    dtype: string, semantic_role: completion}
      - {name: helpfulness, dtype: int64,  semantic_role: score}
      - {name: correctness, dtype: int64,  semantic_role: score}
      - {name: coherence,   dtype: int64,  semantic_role: score}
      - {name: complexity,  dtype: int64,  semantic_role: score}
      - {name: verbosity,   dtype: int64,  semantic_role: score}
    stats:
      prompt:   {text: {chars: {p50: 320, p95: 2200, p99: 5600, max: 12000}},
                 quality: {whitespace_ratio: 0.16, non_ascii_ratio: 0.004, repetition_score: 0.02}}
      response: {text: {chars: {p50: 1350, p95: 3900, p99: 6200, max: 10500}},
                 quality: {whitespace_ratio: 0.15, non_ascii_ratio: 0.003, repetition_score: 0.04}}
      helpfulness: {numeric: {min: 0, max: 4, mean: 2.8}, categorical: {distinct_count: 5}}
      correctness: {numeric: {min: 0, max: 4, mean: 2.9}, categorical: {distinct_count: 5}}
      coherence:   {numeric: {min: 0, max: 4, mean: 3.5}, categorical: {distinct_count: 5}}
      complexity:  {numeric: {min: 0, max: 4, mean: 1.6}, categorical: {distinct_count: 5}}
      verbosity:   {numeric: {min: 0, max: 4, mean: 1.5}, categorical: {distinct_count: 5}}
    classification:
      modality: text
      dataset_type: scored_response
      format: standard
      prompt_form: explicit
      evidence:
        - {kind: column_name,   detail: "prompt + response pair; five rating columns match score aliases"}
        - {kind: content_probe, detail: "all five ratings bounded 0-4 with 5 distinct values"}
        - {kind: card_metadata, detail: "README tag 'human-feedback' corroborates scored human ratings"}
"""

FIXTURES = {
    "OpenMathReasoning": OPENMATHREASONING,
    "hh-rlhf-helpful-base": HH_RLHF_HELPFUL_BASE,
    "HelpSteer2": HELPSTEER2,
}


def _build_profile() -> DatasetProfile:
    """A hand-built profile exercising every model in the contract."""
    return DatasetProfile(
        created_at=datetime(2026, 7, 13, 12, 0, 0),
        profiler_info={"name": "nemo-dataset-profiler", "version": "0.1.0"},
        sampling=SamplingInfo(
            rows_scanned=1024,
            rows_present=2048,
            files_read=2,
            files_present=2,
            per_file_row_cap=512,
            seed=7,
        ),
        partitions=[
            PartitionProfile(
                source_dir=None,
                file_formats=["parquet"],
                stats_complete=False,
                splits=[
                    SplitProfile(
                        name="train",
                        canonical="train",
                        num_examples=2048,
                        files=[
                            FileRecord(
                                path="train-00000.parquet",
                                size_bytes=123,
                                checksum="sha256:ab",
                                file_format="parquet",
                                read_strategy="head",
                                num_rows=2048,
                            )
                        ],
                    )
                ],
                features=[
                    FeatureSchema(name="prompt", dtype="string", semantic_role="prompt"),
                    FeatureSchema(name="response", dtype="string", semantic_role="completion"),
                ],
                stats={
                    "prompt": ColumnStats(text=None),
                    "response": ColumnStats(numeric=None),
                },
                classification=PartitionClassification(
                    dataset_type="prompt_completion",
                    format="standard",
                    prompt_form="explicit",
                    verifiability=Verifiability(
                        method="extractable_final_answer",
                        coverage=0.9,
                        evidence=[Evidence(kind="content_probe", detail="ends with #### in 90% of rows")],
                    ),
                    evidence=[Evidence(kind="column_name", detail="prompt + response pair")],
                ),
            )
        ],
    )


def test_schema_version_defaults_to_constant():
    profile = _build_profile()
    assert profile.profile_schema_version == PROFILE_SCHEMA_VERSION == "1.0"


def test_round_trip_json_is_lossless():
    profile = _build_profile()
    restored = DatasetProfile.model_validate_json(profile.model_dump_json())
    assert restored == profile


@pytest.mark.parametrize("name", list(FIXTURES))
def test_fixture_deserializes(name):
    """Every fixture loads into the contract and round-trips."""
    profile = DatasetProfile.model_validate(yaml.safe_load(FIXTURES[name]))
    assert profile.profile_schema_version == "1.0"
    assert profile.partitions[0].name == "default"
    # Round-trip through JSON is lossless.
    assert DatasetProfile.model_validate_json(profile.model_dump_json()) == profile


def test_openmathreasoning_locks_contract_shape():
    profile = DatasetProfile.model_validate(yaml.safe_load(OPENMATHREASONING))
    part = profile.partitions[0]
    assert part.classification.dataset_type == "prompt_completion"
    assert part.classification.format == "conversational"
    # semantic_role is stacked on the feature node; message struct spelled out under items.
    prompt_feature = part.features[0]
    assert prompt_feature.name == "prompt"
    assert prompt_feature.dtype == "messages"
    assert prompt_feature.semantic_role == "prompt"
    assert prompt_feature.items.fields[0].name == "role"
    # Verifiability carries its own coverage + scoped evidence.
    verify = part.classification.verifiability
    assert verify.method == "extractable_final_answer"
    assert verify.coverage == pytest.approx(0.81)
    # Message stats fold into the messages block.
    assert part.stats["prompt"].messages.ends_with_assistant_rate == 0.0
    assert part.stats["completion"].messages.roles_seen == ["assistant"]


def test_helpsteer2_flat_schema_and_no_verifiability():
    profile = DatasetProfile.model_validate(yaml.safe_load(HELPSTEER2))
    part = profile.partitions[0]
    assert part.classification.dataset_type == "scored_response"
    assert part.classification.format == "standard"
    # Absence of a verifiability object *is* the "not verifiable" claim.
    assert part.classification.verifiability is None
    # Physical column name != role (response -> completion).
    response_feature = next(f for f in part.features if f.name == "response")
    assert response_feature.semantic_role == "completion"
    # Bounded rating scale corroborated by cardinality.
    assert part.stats["helpfulness"].categorical.distinct_count == 5
    assert part.stats["helpfulness"].numeric.max == 4.0
    # card_metadata evidence survives (declared card tags corroborate, never override).
    kinds = {e.kind for e in part.classification.evidence}
    assert "card_metadata" in kinds


def test_semantic_role_reachable_at_any_depth():
    """A role marker nested inside a response list (e.g. a rank) is reachable; a flat column->role
    dict could not address it."""
    answers = FeatureSchema(
        name="answers",
        dtype="list",
        items=FeatureSchema(
            dtype="struct",
            fields=[
                FeatureSchema(name="answer", dtype="string", semantic_role="completion"),
                FeatureSchema(name="model", dtype="string", semantic_role="provenance"),
                FeatureSchema(name="rank", dtype="int64", semantic_role="rank"),
            ],
        ),
    )
    assert answers.items.fields[2].semantic_role == "rank"
    # Round-trips through JSON without losing the nested marker.
    restored = FeatureSchema.model_validate_json(answers.model_dump_json())
    assert restored.items.fields[2].semantic_role == "rank"


def test_vocabularies_are_open():
    """Unknown vocabulary values must be accepted so the vocabulary can grow."""
    classification = PartitionClassification(
        modality="video_text",
        dataset_type="some_future_type",
        format="mixed",
    )
    assert classification.dataset_type == "some_future_type"
    feature = FeatureSchema(dtype="tensor", semantic_role="a_role_added_next_year")
    assert feature.semantic_role == "a_role_added_next_year"


def test_fields_and_items_are_mutually_exclusive():
    """A node cannot be both a named-field container and a single-element container."""
    with pytest.raises(ValidationError, match="mutually exclusive"):
        FeatureSchema(
            name="broken",
            dtype="struct",
            fields=[FeatureSchema(name="a", dtype="string")],
            items=FeatureSchema(dtype="string"),
        )


def test_container_shape_is_not_pinned_to_known_dtypes():
    """The exclusivity check must not become a dtype whitelist: a container dtype added by a newer
    profiler still loads on an older reader, which is what the open vocabulary buys."""
    future_map = FeatureSchema(name="attrs", dtype="map", fields=[FeatureSchema(name="k", dtype="string")])
    assert [field.name for field in future_map.fields or []] == ["k"]
    future_tensor = FeatureSchema(name="embedding", dtype="tensor", fixed_length=768)
    assert future_tensor.fixed_length == 768


def test_unknown_fields_are_ignored_for_forward_compat():
    """A profile written by a newer minor version (extra fields) still loads on an older reader."""
    doc = yaml.safe_load(HELPSTEER2)
    doc["some_future_top_level_field"] = {"anything": 1}
    doc["partitions"][0]["classification"]["future_axis"] = "value"
    profile = DatasetProfile.model_validate(doc)
    assert profile.partitions[0].classification.dataset_type == "scored_response"


def test_file_formats_must_not_omit_a_format_its_files_carry():
    # The partition summary is derived from the records, so the two can drift. A summary claiming
    # one format while a file says otherwise would report the partition as homogeneous when it is
    # not -- the very assumption that made format a partition dimension and cost names their
    # stability. Subset, not equality, so a profile written before per-file formats still loads.
    doc = yaml.safe_load(HELPSTEER2)
    doc["partitions"][0]["splits"][0]["files"][0]["file_format"] = "jsonl"
    with pytest.raises(ValueError, match="file_formats omits"):
        DatasetProfile.model_validate(doc)


def test_a_partition_written_before_per_file_formats_still_loads():
    doc = yaml.safe_load(HELPSTEER2)
    for split in doc["partitions"][0]["splits"]:
        for file in split["files"]:
            del file["file_format"]
    profile = DatasetProfile.model_validate(doc)
    assert profile.partitions[0].splits[0].files[0].file_format is None


def test_a_profile_written_before_the_digest_was_dropped_still_loads():
    # `content_digest` was removed rather than repaired: it froze "which files count as inputs" into
    # stored data at write time, and that judgment moves. Profiles already written with it have to
    # keep loading, or removing it would break every one of them at once — the very failure mode the
    # removal exists to avoid.
    doc = yaml.safe_load(HELPSTEER2)
    doc["content_digest"] = "sha256:7be1c0ffee"
    profile = DatasetProfile.model_validate(doc)
    assert not hasattr(profile, "content_digest")
    assert profile.partitions[0].classification.dataset_type == "scored_response"


def test_quantiles_and_message_stats_construct():
    """Smoke-check the leaf stat models are wired as documented."""
    stats = MessageStats(
        turns=Quantiles(p50=1, p95=3, p99=5, max=9),
        content_chars=Quantiles(p50=100, p95=500, p99=900, max=2000),
        roles_seen=["user", "assistant", "tool"],
        ends_with_assistant_rate=1.0,
        valid_alternation_rate=0.98,
        has_tool_calls=True,
    )
    assert stats.turns.max == 9
    assert stats.has_tool_calls is True
