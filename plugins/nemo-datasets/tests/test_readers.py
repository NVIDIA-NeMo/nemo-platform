# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the file-source seam and the per-format readers."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from nemo_datasets_plugin.profiler.file_source import FileEntry, LocalFileSource
from nemo_datasets_plugin.profiler.readers import detect_format, get_reader

PARQUET_ROWS = [
    {"prompt": "a", "score": 1},
    {"prompt": "b", "score": 2},
    {"prompt": "c", "score": 3},
]


def _write_parquet(path, rows):
    pq.write_table(pa.Table.from_pylist(rows), path)


# --- file source ---------------------------------------------------------------------------------


def test_local_file_source_lists_sorted_with_sizes(tmp_path):
    (tmp_path / "b.jsonl").write_text('{"x": 1}\n')
    (tmp_path / "a.parquet").write_bytes(b"not-real-parquet")  # only listed here, not parsed
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.jsonl").write_text("{}\n")

    entries = LocalFileSource(tmp_path).list_files()

    assert [e.path for e in entries] == ["a.parquet", "b.jsonl", "sub/c.jsonl"]
    assert all(e.size_bytes > 0 for e in entries)
    assert all(e.checksum is None for e in entries)  # local sources report no checksum


def test_local_file_source_open_reads_bytes(tmp_path):
    (tmp_path / "f.jsonl").write_text('{"x": 1}\n')
    with LocalFileSource(tmp_path).open("f.jsonl") as stream:
        assert stream.read() == b'{"x": 1}\n'


def test_local_file_source_rejects_non_directory(tmp_path):
    target = tmp_path / "f"
    target.write_text("x")
    with pytest.raises(NotADirectoryError):
        LocalFileSource(target)


# --- registry ------------------------------------------------------------------------------------


def test_detect_format_by_extension():
    assert detect_format("data/train-00000-of-00003.parquet") == "parquet"
    assert detect_format("x.jsonl") == "jsonl"
    assert detect_format("x.ndjson") == "jsonl"
    assert detect_format("README.md") is None


def test_get_reader_unknown_format_raises():
    with pytest.raises(KeyError):
        get_reader("arrow")


# --- parquet reader ------------------------------------------------------------------------------


def test_parquet_reader_reads_schema_rows_and_exact_count(tmp_path):
    _write_parquet(tmp_path / "d.parquet", PARQUET_ROWS)
    result = get_reader("parquet").read(LocalFileSource(tmp_path), FileEntry("d.parquet", 0))

    assert result.num_rows == 3  # exact, from the footer
    assert result.rows_scanned == 3
    assert result.rows == PARQUET_ROWS
    assert set(result.arrow_schema.names) == {"prompt", "score"}


def test_parquet_reader_row_cap_bounds_rows_but_keeps_exact_count(tmp_path):
    _write_parquet(tmp_path / "d.parquet", PARQUET_ROWS)
    result = get_reader("parquet").read(LocalFileSource(tmp_path), FileEntry("d.parquet", 0), row_cap=2)

    assert result.num_rows == 3  # footer count is unaffected by sampling
    assert result.rows_scanned == 2
    assert result.rows == PARQUET_ROWS[:2]


def test_parquet_reader_zero_cap_reads_no_rows(tmp_path):
    _write_parquet(tmp_path / "d.parquet", PARQUET_ROWS)
    result = get_reader("parquet").read(LocalFileSource(tmp_path), FileEntry("d.parquet", 0), row_cap=0)

    assert result.rows == []
    assert result.num_rows == 3
    assert result.arrow_schema is not None  # schema is still known without reading rows


# --- jsonl reader --------------------------------------------------------------------------------


def test_jsonl_reader_full_read_is_exact_and_skips_blanks(tmp_path):
    (tmp_path / "d.jsonl").write_text('{"a": 1}\n\n{"a": 2}\n')
    result = get_reader("jsonl").read(LocalFileSource(tmp_path), FileEntry("d.jsonl", 0))

    assert result.rows == [{"a": 1}, {"a": 2}]
    assert result.num_rows == 2  # exact on a full read
    assert result.arrow_schema is None  # jsonl declares no schema


def test_jsonl_reader_row_cap_leaves_count_unknown(tmp_path):
    (tmp_path / "d.jsonl").write_text('{"a": 1}\n{"a": 2}\n{"a": 3}\n')
    result = get_reader("jsonl").read(LocalFileSource(tmp_path), FileEntry("d.jsonl", 0), row_cap=2)

    assert result.rows == [{"a": 1}, {"a": 2}]
    assert result.rows_scanned == 2
    assert result.num_rows is None  # a partial read can't assert the total
