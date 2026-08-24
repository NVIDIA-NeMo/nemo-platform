# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for the ranged-read fileset source."""

import io
import json
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from nemo_datasets_plugin.fileset_source import FilesetFileSource, _RangedFile
from nemo_datasets_plugin.profiler.pipeline import profile


class _FakeFilesClient:
    """Serves an in-memory fileset, honouring the Range header the way the Files service does.

    Records every range actually requested so tests can assert on what a read cost over the wire,
    which is the whole point of this source.
    """

    def __init__(self, files: dict[str, bytes], *, ignore_range: bool = False):
        self.files = files
        self.ignore_range = ignore_range
        self.ranges: list[tuple[str, int, int]] = []
        self._pending_range: tuple[int, int] | None = None

    def with_headers(self, headers):
        clone = _FakeFilesClient(self.files, ignore_range=self.ignore_range)
        clone.ranges = self.ranges  # share the log with the parent
        header = headers.get("Range", "")
        assert header.startswith("bytes="), f"expected a byte range, got {header!r}"
        start, _, end = header.removeprefix("bytes=").partition("-")
        clone._pending_range = (int(start), int(end))
        return clone

    def list_files(self, *, workspace, name):
        data = [SimpleNamespace(path=path, size=len(body)) for path, body in self.files.items()]
        return SimpleNamespace(data=lambda: SimpleNamespace(data=data))

    def download_file(self, *, workspace, name, path):
        body = self.files[path]
        assert self._pending_range is not None, "download_file called without a Range header"
        start, end = self._pending_range
        self.ranges.append((path, start, end))
        # A server that ignores Range replies with the whole body instead of a 206.
        chunk = body if self.ignore_range else body[start : end + 1]
        return SimpleNamespace(read=lambda: chunk)


def _ranged(body: bytes, **kwargs) -> _RangedFile:
    return _RangedFile(lambda start, end: body[start : end + 1], len(body), **kwargs)


# --- _RangedFile ---------------------------------------------------------------------------------


def test_reads_whole_content_across_block_boundaries():
    body = bytes(range(256)) * 4  # 1024 bytes
    assert _ranged(body, block_size=100).read() == body


def test_seek_modes_agree_with_a_real_file():
    body = bytes(range(256))
    ranged = _ranged(body, block_size=32)
    reference = io.BytesIO(body)
    for offset, whence in [(10, io.SEEK_SET), (5, io.SEEK_CUR), (-8, io.SEEK_END), (0, io.SEEK_SET)]:
        assert ranged.seek(offset, whence) == reference.seek(offset, whence)
        assert ranged.read(7) == reference.read(7)


def test_read_past_eof_returns_nothing():
    ranged = _ranged(b"0123456789", block_size=4)
    ranged.seek(50)
    assert ranged.read() == b""
    assert ranged.tell() == 50  # seeking past the end is legal and does not move on a short read


def test_read_clamps_at_the_final_partial_block():
    body = b"0123456789"  # 10 bytes over a block size that does not divide it
    ranged = _ranged(body, block_size=4)
    ranged.seek(8)
    assert ranged.read(99) == b"89"


def test_negative_seek_is_rejected():
    with pytest.raises(OSError):
        _ranged(b"abc").seek(-1)


def test_blocks_are_cached_so_rereads_cost_nothing():
    ranged = _ranged(bytes(1000), block_size=100)
    ranged.read(250)  # spans blocks 0..2
    assert ranged.requests == 3
    ranged.seek(0)
    ranged.read(250)  # same blocks, now cached
    assert ranged.requests == 3


def test_cache_is_bounded():
    ranged = _ranged(bytes(1000), block_size=100, max_cached_blocks=2)
    ranged.read(1000)  # touches 10 blocks
    assert len(ranged._blocks) == 2


def test_a_server_ignoring_range_still_reads_correctly():
    # Some proxies answer 200 with the whole body; the window must still be sliced out, or every
    # subsequent read would be misaligned.
    body = bytes(range(256))
    ranged = _RangedFile(lambda start, end: body, len(body), block_size=32)
    ranged.seek(100)
    assert ranged.read(10) == body[100:110]


def test_a_truncated_range_reply_raises_instead_of_reading_short():
    # A short block cannot be placed. Caching it would make the next read return zero bytes, which
    # the BufferedReader reads as EOF — so the profile would come out quietly wrong rather than
    # not at all.
    body = bytes(range(256))
    ranged = _RangedFile(lambda start, end: body[start : end + 1][:5], len(body), block_size=32)
    with pytest.raises(OSError, match="expected 32"):
        ranged.read(64)


def test_an_over_long_reply_that_is_not_the_whole_body_raises():
    # Neither a valid range nor a recognisable whole-body reply, so there is no way to know which
    # window these bytes are; guessing an offset would silently corrupt every read after it.
    body = bytes(range(256))
    ranged = _RangedFile(lambda start, end: body[:40], len(body), block_size=32)
    with pytest.raises(OSError):
        ranged.read(10)


def test_empty_file_reads_empty_without_a_request():
    ranged = _ranged(b"")
    assert ranged.read() == b""
    assert ranged.requests == 0


# --- FilesetFileSource ---------------------------------------------------------------------------


def test_list_files_is_sorted_with_sizes_and_no_checksum():
    client = _FakeFilesClient({"b.jsonl": b"22", "a.parquet": b"1"})
    entries = FilesetFileSource(client, workspace="ws", fileset="fs").list_files()

    assert [e.path for e in entries] == ["a.parquet", "b.jsonl"]
    assert [e.size_bytes for e in entries] == [1, 2]
    assert all(e.checksum is None for e in entries)  # the listing carries no digest


def test_open_unknown_path_raises():
    source = FilesetFileSource(_FakeFilesClient({"a.jsonl": b"{}"}), workspace="ws", fileset="fs")
    with pytest.raises(FileNotFoundError):
        source.open("nope.jsonl")


def test_open_lists_lazily_when_not_listed_first():
    source = FilesetFileSource(_FakeFilesClient({"a.jsonl": b'{"x": 1}\n'}), workspace="ws", fileset="fs")
    with source.open("a.jsonl") as stream:  # no list_files() call beforehand
        assert stream.read() == b'{"x": 1}\n'


def test_jsonl_reads_sequentially_through_the_buffer():
    body = b"".join(json.dumps({"a": i}).encode() + b"\n" for i in range(200))
    client = _FakeFilesClient({"train.jsonl": body})
    source = FilesetFileSource(client, workspace="ws", fileset="fs", block_size=256)

    with source.open("train.jsonl") as stream:
        assert sum(1 for _ in stream) == 200


def test_parquet_reads_only_part_of_a_file(tmp_path):
    # The point of the source: pyarrow reads a parquet schema and its first rows without the file
    # ever being transferred whole. Block size is set well below the file size here so the fetch
    # granularity is actually exercised; at the default a file this small is one block anyway.
    rows = [{"prompt": f"question {i}", "completion": f"answer {i}"} for i in range(20_000)]
    path = tmp_path / "train-00000-of-00001.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path, row_group_size=1000)
    body = path.read_bytes()

    client = _FakeFilesClient({"train-00000-of-00001.parquet": body})
    source = FilesetFileSource(client, workspace="ws", fileset="fs", block_size=32 * 1024)

    with source.open("train-00000-of-00001.parquet") as stream:
        parquet_file = pq.ParquetFile(stream)
        assert parquet_file.metadata.num_rows == 20_000  # footer read, exact count
        assert set(parquet_file.schema_arrow.names) == {"prompt", "completion"}
        first = next(parquet_file.iter_batches(batch_size=100)).to_pylist()

    assert first[0] == rows[0]
    fetched = sum(end - start + 1 for _, start, end in client.ranges)
    assert fetched < len(body), "reading a sample should not transfer the whole file"


def test_a_file_smaller_than_a_block_costs_one_request():
    # The flip side: block-aligned fetching must not make small files worse. One request, and no
    # more bytes than the file holds.
    body = b'{"a": 1}\n' * 100
    client = _FakeFilesClient({"train.jsonl": body})
    source = FilesetFileSource(client, workspace="ws", fileset="fs")

    with source.open("train.jsonl") as stream:
        assert stream.read() == body

    assert len(client.ranges) == 1
    _, start, end = client.ranges[0]
    assert (start, end) == (0, len(body) - 1)


def test_profile_runs_end_to_end_over_the_source(tmp_path):
    # The seam holds: the pipeline is unchanged by which FileSource it is handed.
    train = tmp_path / "train.parquet"
    pq.write_table(pa.Table.from_pylist([{"prompt": "q", "completion": "a"}] * 50), train)
    client = _FakeFilesClient(
        {
            "train-00000-of-00001.parquet": train.read_bytes(),
            "README.md": b"a dataset card",
        }
    )

    result = profile(FilesetFileSource(client, workspace="ws", fileset="fs"))

    partition = result.partitions[0]
    assert partition.file_formats == ["parquet"]
    assert [f.name for f in partition.features] == ["prompt", "completion"]
    assert partition.classification.dataset_type == "prompt_completion"
    assert result.partitions[0].splits[0].num_examples == 50
