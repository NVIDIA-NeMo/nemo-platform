# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for dataset utilities.

These tests are CPU-safe and run in regular CI - no GPU dependencies.
"""

import json
from pathlib import Path

import pytest
from nmp.customizer.tasks.training.datasets.preparation import (
    MERGED_DIR,
    TRAIN_FILE,
    VAL_FILE,
    DatasetFormatError,
    DatasetSchema,
    PreparedDataset,
    compute_val_check_interval,
    count_jsonl_samples,
    detect_dataset_schema,
    discover_dataset_files,
    prepare_dataset,
)


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    """Create and return a dataset directory for tests."""
    path = tmp_path / "dataset"
    path.mkdir(parents=True)
    return path


def _write_jsonl(file_path: Path, samples: list[dict]) -> None:
    """Helper to write JSONL samples to a file."""
    with open(file_path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")


class TestDetectDatasetSchema:
    """Tests for detect_dataset_schema function."""

    def test_detects_chat_format(self, dataset_dir: Path):
        """Test detection of OpenAI chat format."""
        file_path = dataset_dir / "chat.jsonl"
        _write_jsonl(
            file_path,
            [
                {
                    "messages": [
                        {"role": "user", "content": "Hello"},
                        {"role": "assistant", "content": "Hi there!"},
                    ]
                }
            ],
        )

        schema, keys = detect_dataset_schema(file_path)

        assert schema == DatasetSchema.CHAT
        assert keys is None

    def test_detects_sft_format(self, dataset_dir: Path):
        """Test detection of standard SFT format."""
        file_path = dataset_dir / "sft.jsonl"
        _write_jsonl(file_path, [{"prompt": "Question?", "completion": "Answer."}])

        schema, keys = detect_dataset_schema(file_path)

        assert schema == DatasetSchema.SFT
        assert keys == ("prompt", "completion")

    def test_detects_custom_format_with_template(self, dataset_dir: Path):
        """Test detection of custom format using prompt_template."""
        file_path = dataset_dir / "custom.jsonl"
        _write_jsonl(file_path, [{"input": "Hello", "output": "World"}])

        schema, keys = detect_dataset_schema(file_path, prompt_template="{input} {output}")

        assert schema == DatasetSchema.CUSTOM
        assert keys == ("input", "output")

    def test_fallback_to_first_two_string_columns(self, dataset_dir: Path):
        """Test fallback when no standard format detected."""
        file_path = dataset_dir / "unknown.jsonl"
        _write_jsonl(file_path, [{"question": "What?", "answer": "This.", "extra": 123}])

        schema, keys = detect_dataset_schema(file_path)

        assert schema == DatasetSchema.SFT
        # First two string columns
        assert keys == ("question", "answer")

    def test_raises_on_invalid_json(self, dataset_dir: Path):
        """Test error handling for invalid JSON."""
        file_path = dataset_dir / "invalid.jsonl"
        file_path.write_text("not valid json\n")

        with pytest.raises(DatasetFormatError, match="Invalid JSON"):
            detect_dataset_schema(file_path)

    def test_raises_when_template_keys_not_found(self, dataset_dir: Path):
        """Test error when prompt_template keys don't exist in data."""
        file_path = dataset_dir / "data.jsonl"
        _write_jsonl(file_path, [{"a": "1", "b": "2"}])

        with pytest.raises(DatasetFormatError, match="not found in dataset"):
            detect_dataset_schema(file_path, prompt_template="{missing1} {missing2}")

    def test_raises_when_template_has_wrong_placeholder_count(self, dataset_dir: Path):
        """Test error when prompt_template has wrong number of placeholders."""
        file_path = dataset_dir / "data.jsonl"
        _write_jsonl(file_path, [{"a": "1"}])

        with pytest.raises(DatasetFormatError, match="exactly 2 placeholders"):
            detect_dataset_schema(file_path, prompt_template="{only_one}")

    def test_detects_embedding_format(self, dataset_dir: Path):
        """Test detection of embedding/retrieval format."""
        file_path = dataset_dir / "embedding.jsonl"
        _write_jsonl(
            file_path,
            [
                {
                    "query": "What is machine learning?",
                    "pos_doc": "Machine learning is a subset of AI...",
                    "neg_doc": ["Cooking is an art...", "Sports are fun..."],
                }
            ],
        )

        schema, keys = detect_dataset_schema(file_path)

        assert schema == DatasetSchema.EMBEDDING
        assert keys == ("query", "pos_doc", "neg_doc")

    def test_embedding_format_requires_all_fields(self, dataset_dir: Path):
        """Test that embedding detection requires all three fields."""
        file_path = dataset_dir / "partial.jsonl"
        # Missing neg_doc
        _write_jsonl(file_path, [{"query": "What?", "pos_doc": "Answer"}])

        schema, keys = detect_dataset_schema(file_path)

        # Should fall back to SFT format, not embedding
        assert schema == DatasetSchema.SFT
        assert keys == ("query", "pos_doc")


class TestCountJsonlSamples:
    """Tests for count_jsonl_samples function."""

    def test_counts_non_empty_lines(self, dataset_dir: Path):
        """Test counting non-empty lines."""
        file_path = dataset_dir / "data.jsonl"
        _write_jsonl(file_path, [{"a": 1}, {"a": 2}, {"a": 3}])

        count = count_jsonl_samples(file_path)

        assert count == 3

    def test_ignores_empty_lines(self, dataset_dir: Path):
        """Test that empty lines are not counted."""
        file_path = dataset_dir / "data.jsonl"
        file_path.write_text('{"a": 1}\n\n{"a": 2}\n\n\n{"a": 3}\n')

        count = count_jsonl_samples(file_path)

        assert count == 3

    def test_handles_empty_file(self, dataset_dir: Path):
        """Test counting empty file."""
        file_path = dataset_dir / "empty.jsonl"
        file_path.write_text("")

        count = count_jsonl_samples(file_path)

        assert count == 0


class TestComputeValCheckInterval:
    """Tests for compute_val_check_interval function."""

    def test_default_to_end_of_epoch(self):
        """Test default behavior: validate at end of epoch."""
        interval = compute_val_check_interval(steps_per_epoch=100, max_steps=500)
        assert interval == 100

    def test_default_caps_at_max_steps(self):
        """Test default caps at max_steps when max_steps < steps_per_epoch."""
        interval = compute_val_check_interval(steps_per_epoch=100, max_steps=50)
        assert interval == 50

    def test_float_fraction_of_epoch(self):
        """Test float <= 1.0 interpreted as fraction of epoch."""
        interval = compute_val_check_interval(
            steps_per_epoch=100,
            max_steps=500,
            val_check_interval=0.5,
        )
        assert interval == 50  # 50% of epoch

    def test_small_fraction_minimum_one(self):
        """Test small fractions result in at least 1 step."""
        interval = compute_val_check_interval(
            steps_per_epoch=10,
            max_steps=100,
            val_check_interval=0.01,
        )
        assert interval == 1

    def test_integer_absolute_steps(self):
        """Test integer interpreted as absolute step count."""
        interval = compute_val_check_interval(
            steps_per_epoch=100,
            max_steps=500,
            val_check_interval=25,
        )
        assert interval == 25

    def test_large_float_as_absolute_steps(self):
        """Test float > 1.0 treated as absolute steps."""
        interval = compute_val_check_interval(
            steps_per_epoch=100,
            max_steps=500,
            val_check_interval=25.0,
        )
        assert interval == 25

    def test_caps_at_max_steps_minus_one(self):
        """Test interval is capped to allow at least one validation."""
        interval = compute_val_check_interval(
            steps_per_epoch=100,
            max_steps=50,
            val_check_interval=200,
        )
        assert interval == 49  # max_steps - 1

    def test_raises_on_negative(self):
        """Test error on negative interval."""
        with pytest.raises(ValueError, match="cannot be negative"):
            compute_val_check_interval(
                steps_per_epoch=100,
                max_steps=500,
                val_check_interval=-1,
            )


class TestDiscoverDatasetFiles:
    """Tests for discover_dataset_files function."""

    def test_single_file_treated_as_training(self, dataset_dir: Path):
        """Test single file is treated as training data."""
        file_path = dataset_dir / "data.jsonl"
        _write_jsonl(file_path, [{"a": 1}])

        train_files, val_files = discover_dataset_files(file_path)

        assert len(train_files) == 1
        assert train_files[0] == file_path
        assert len(val_files) == 0

    def test_discovers_train_pattern_files(self, dataset_dir: Path):
        """Test discovery of files matching train* pattern."""
        train_file = dataset_dir / "train.jsonl"
        _write_jsonl(train_file, [{"a": 1}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 1
        assert train_files[0].name == "train.jsonl"
        assert len(val_files) == 0

    def test_discovers_val_pattern_files(self, dataset_dir: Path):
        """Test discovery of files matching val* pattern."""
        train_file = dataset_dir / "train.jsonl"
        val_file = dataset_dir / "validation.jsonl"
        _write_jsonl(train_file, [{"a": 1}])
        _write_jsonl(val_file, [{"a": 2}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 1
        assert len(val_files) == 1
        assert val_files[0].name == "validation.jsonl"

    def test_discovers_files_in_subdirectories(self, dataset_dir: Path):
        """Test discovery of files in train/ and val/ subdirectories."""
        train_dir = dataset_dir / "train"
        train_dir.mkdir()
        val_dir = dataset_dir / "validation"
        val_dir.mkdir()

        train_file = train_dir / "data.jsonl"
        val_file = val_dir / "data.jsonl"
        _write_jsonl(train_file, [{"a": 1}])
        _write_jsonl(val_file, [{"a": 2}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 1
        assert len(val_files) == 1

    def test_fallback_single_jsonl_as_training(self, dataset_dir: Path):
        """Test fallback: single JSONL without naming pattern treated as training."""
        file_path = dataset_dir / "my_data.jsonl"
        _write_jsonl(file_path, [{"a": 1}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 1
        assert len(val_files) == 0

    def test_fallback_lone_json_as_training(self, dataset_dir: Path):
        """Lone root .json file (no train/val pattern) is claimed as training."""
        file_path = dataset_dir / "data.json"
        _write_jsonl(file_path, [{"a": 1}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 1
        assert train_files[0].name == "data.json"
        assert len(val_files) == 0

    def test_fallback_mixed_json_and_jsonl_both_claimed(self, dataset_dir: Path):
        """Lone root .jsonl + .json (mixed, no pattern) → both claimed as training."""
        jsonl_file = dataset_dir / "my_data.jsonl"
        json_file = dataset_dir / "extra.json"
        _write_jsonl(jsonl_file, [{"a": 1}])
        _write_jsonl(json_file, [{"a": 2}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 2
        assert {f.name for f in train_files} == {"my_data.jsonl", "extra.json"}
        assert len(val_files) == 0

    def test_fallback_multiple_json_all_claimed_as_training(self, dataset_dir: Path):
        """Multiple root .json files (no pattern) → all claimed as training with warning."""
        for name in ("a.json", "b.json", "c.json"):
            _write_jsonl(dataset_dir / name, [{"a": 1}])

        train_files, val_files = discover_dataset_files(dataset_dir)

        assert len(train_files) == 3
        assert len(val_files) == 0

    def test_raises_when_no_files_found(self, dataset_dir: Path):
        """Test error when no training files found."""
        with pytest.raises(DatasetFormatError, match="No training files found"):
            discover_dataset_files(dataset_dir)

    def test_raises_when_path_not_exists(self, tmp_path: Path):
        """Test error when path doesn't exist."""
        with pytest.raises(DatasetFormatError, match="does not exist"):
            discover_dataset_files(tmp_path / "nonexistent")


class TestPrepareDataset:
    """Tests for prepare_dataset function."""

    def test_single_file_creates_split(self, dataset_dir: Path):
        """Test single file is split into train and validation."""
        file_path = dataset_dir / "data.jsonl"
        samples = [{"text": f"sample {i}"} for i in range(20)]
        _write_jsonl(file_path, samples)

        result = prepare_dataset(file_path, val_split_ratio=0.2, seed=42)

        assert isinstance(result, PreparedDataset)
        assert result.train_file.exists()
        assert result.validation_file.exists()
        # 20% of 20 = 4 validation samples
        assert result.validation_samples == 4
        assert result.train_samples == 16
        # Total should equal original
        assert result.train_samples + result.validation_samples == 20

    def test_merges_multiple_train_files(self, dataset_dir: Path):
        """Test multiple training files are merged."""
        train_file1 = dataset_dir / "train_part1.jsonl"
        train_file2 = dataset_dir / "train_part2.jsonl"
        _write_jsonl(train_file1, [{"text": f"a{i}"} for i in range(5)])
        _write_jsonl(train_file2, [{"text": f"b{i}"} for i in range(5)])

        # Create validation file to prevent auto-split
        val_file = dataset_dir / "validation.jsonl"
        _write_jsonl(val_file, [{"text": "val"}])

        result = prepare_dataset(dataset_dir)

        assert result.train_samples == 10  # 5 + 5
        assert result.validation_samples == 1

    def test_uses_existing_validation_files(self, dataset_dir: Path):
        """Test existing validation files are used instead of auto-split."""
        train_file = dataset_dir / "train.jsonl"
        val_file = dataset_dir / "validation.jsonl"
        _write_jsonl(train_file, [{"text": f"train{i}"} for i in range(10)])
        _write_jsonl(val_file, [{"text": f"val{i}"} for i in range(3)])

        result = prepare_dataset(dataset_dir)

        assert result.train_samples == 10
        assert result.validation_samples == 3

    def test_output_dir_customization(self, dataset_dir: Path, tmp_path: Path):
        """Test custom output directory."""
        file_path = dataset_dir / "data.jsonl"
        _write_jsonl(file_path, [{"text": f"sample {i}"} for i in range(10)])

        custom_output = tmp_path / "custom_output"
        result = prepare_dataset(file_path, output_dir=custom_output)

        assert result.merged_dir == custom_output
        assert result.train_file.parent == custom_output

    def test_reproducible_splits_with_seed(self, dataset_dir: Path):
        """Test that splits are reproducible with same seed."""
        file_path = dataset_dir / "data.jsonl"
        samples = [{"text": f"sample {i}"} for i in range(100)]
        _write_jsonl(file_path, samples)

        # Run twice with same seed
        result1 = prepare_dataset(file_path, seed=123)
        # Re-create file (prepare_dataset modifies it)
        _write_jsonl(file_path, samples)
        result2 = prepare_dataset(file_path, seed=123)

        # Read and compare
        train1 = result1.train_file.read_text()
        train2 = result2.train_file.read_text()
        assert train1 == train2

    def test_default_output_in_merged_subdir(self, dataset_dir: Path):
        """Test default output is in merged/ subdirectory."""
        file_path = dataset_dir / "train.jsonl"
        val_file = dataset_dir / "val.jsonl"
        _write_jsonl(file_path, [{"text": "train"}])
        _write_jsonl(val_file, [{"text": "val"}])

        result = prepare_dataset(dataset_dir)

        assert result.merged_dir == dataset_dir / MERGED_DIR
        assert result.train_file.name == TRAIN_FILE
        assert result.validation_file.name == VAL_FILE


class TestMergeFilesIntegration:
    """Integration tests for file merging behavior."""

    def test_merged_file_contains_all_samples(self, dataset_dir: Path):
        """Test merged file contains all samples from source files."""
        file1 = dataset_dir / "train_a.jsonl"
        file2 = dataset_dir / "train_b.jsonl"
        samples1 = [{"id": 1, "text": "a"}, {"id": 2, "text": "b"}]
        samples2 = [{"id": 3, "text": "c"}, {"id": 4, "text": "d"}]
        _write_jsonl(file1, samples1)
        _write_jsonl(file2, samples2)

        val_file = dataset_dir / "val.jsonl"
        _write_jsonl(val_file, [{"id": 0}])

        result = prepare_dataset(dataset_dir)

        # Read merged file and verify all samples present
        with open(result.train_file, "r") as f:
            merged_samples = [json.loads(line) for line in f]

        assert len(merged_samples) == 4
        ids = {s["id"] for s in merged_samples}
        assert ids == {1, 2, 3, 4}

    def test_handles_files_without_trailing_newline(self, dataset_dir: Path):
        """Test merging works when files don't end with newline."""
        file1 = dataset_dir / "train_a.jsonl"
        file2 = dataset_dir / "train_b.jsonl"
        # Write without trailing newline
        file1.write_text('{"id": 1}')
        file2.write_text('{"id": 2}')

        val_file = dataset_dir / "val.jsonl"
        _write_jsonl(val_file, [{"id": 0}])

        result = prepare_dataset(dataset_dir)

        assert result.train_samples == 2
