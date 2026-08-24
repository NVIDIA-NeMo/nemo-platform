# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""A :class:`FileSource` over a platform fileset, read through HTTP range requests.

The profiler needs very little of any one file: a parquet footer plus the first row group is
enough to derive the schema and measure a capped sample. Staging whole filesets on local disk to
read that much is the difference between transferring a few megabytes and transferring the whole
dataset.

The Files service already serves ranged GETs, so this module adapts them into the seekable,
read-only file object pyarrow expects. Reads are served from aligned blocks fetched on demand and
cached, which is what keeps parquet's access pattern — seek to the tail for the footer, then jump
between column chunks — from costing a request per seek.

This lives outside ``profiler/`` on purpose: the profiler core knows only the
:class:`~nemo_datasets_plugin.profiler.file_source.FileSource` seam, and keeping the platform SDK
out of its import graph is what lets it be used (and tested) standalone.
"""

from __future__ import annotations

import io
from collections import OrderedDict
from typing import Any, BinaryIO, Callable, Mapping, Protocol

from nemo_datasets_plugin.profiler.file_source import FileEntry

# Bytes per range request. What a capped profile costs is roughly (one block for the footer) plus
# (the first row group), so this sets the floor rather than scaling with the file. Measured against
# a 48 MB / 24-row-group shard, reading the schema and 1000 rows fetched 13.1% of the file at 4 MiB
# (2 requests), 6.5% at 1 MiB (4 requests), and 4.9% at 256 KiB (10 requests) — so a megabyte buys
# most of the saving without paying for the extra round trips. Ranges are clamped to the file size,
# so anything smaller than a block is still exactly one request for exactly its own bytes.
_DEFAULT_BLOCK_SIZE = 1024 * 1024

# Blocks retained per open file. Parquet bounces between the footer and column chunks, so keeping a
# few blocks turns most of that into cache hits; the cap bounds memory at block_size x this.
_DEFAULT_MAX_CACHED_BLOCKS = 8


class FilesetClient(Protocol):
    """The slice of the Files client this source uses.

    Narrower than :class:`~nemo_platform_plugin.files.client.FilesClient` on purpose: it states the
    actual dependency, and it lets the source be exercised without standing up a real client — the
    same reason the profiler depends on ``FileSource`` rather than a concrete source.
    """

    def with_headers(self, headers: Mapping[str, str]) -> "FilesetClient": ...

    def list_files(self, *, workspace: str, name: str) -> Any: ...

    def download_file(self, *, workspace: str, name: str, path: str) -> Any: ...


class _RangedFile(io.RawIOBase):
    """A seekable, read-only file whose contents are fetched in blocks on demand.

    ``fetch_range(start, end)`` must return the bytes of an inclusive byte range, matching HTTP
    Range semantics. Exposes ``requests`` and ``bytes_fetched`` so callers (and tests) can see what
    a read actually cost over the wire.
    """

    def __init__(
        self,
        fetch_range: Callable[[int, int], bytes],
        size: int,
        *,
        block_size: int = _DEFAULT_BLOCK_SIZE,
        max_cached_blocks: int = _DEFAULT_MAX_CACHED_BLOCKS,
    ) -> None:
        if block_size <= 0:
            raise ValueError("block_size must be positive")
        self._fetch_range = fetch_range
        self._size = size
        self._block_size = block_size
        self._max_cached_blocks = max(1, max_cached_blocks)
        self._blocks: OrderedDict[int, bytes] = OrderedDict()
        self._pos = 0
        self.requests = 0
        self.bytes_fetched = 0

    # --- io.RawIOBase ----------------------------------------------------------------------

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            position = offset
        elif whence == io.SEEK_CUR:
            position = self._pos + offset
        elif whence == io.SEEK_END:
            position = self._size + offset
        else:
            raise ValueError(f"invalid whence: {whence!r}")
        if position < 0:
            raise OSError("negative seek position")
        # Seeking past EOF is legal for a file object; the next read simply returns nothing.
        self._pos = position
        return self._pos

    def readinto(self, buffer) -> int:  # noqa: ANN001  (buffer is any writable bytes-like)
        view = memoryview(buffer).cast("B")
        remaining = min(len(view), max(0, self._size - self._pos))
        written = 0
        while written < remaining:
            index = self._pos // self._block_size
            block = self._block(index)
            offset = self._pos - index * self._block_size
            take = min(remaining - written, len(block) - offset)
            if take <= 0:  # pragma: no cover - _block guarantees full blocks, so this cannot happen
                raise OSError(f"block {index} is short at offset {self._pos}; cannot make progress")
            view[written : written + take] = block[offset : offset + take]
            written += take
            self._pos += take
        return written

    def close(self) -> None:
        self._blocks.clear()
        super().close()

    # --- block cache -----------------------------------------------------------------------

    def _block(self, index: int) -> bytes:
        cached = self._blocks.get(index)
        if cached is not None:
            self._blocks.move_to_end(index)
            return cached

        start = index * self._block_size
        end = min(start + self._block_size, self._size) - 1  # inclusive, as HTTP Range wants
        data = self._fetch_range(start, end)
        self.requests += 1
        self.bytes_fetched += len(data)

        expected = end - start + 1
        if len(data) == self._size and expected != self._size:
            # A server (or proxy) that ignores Range answers with the whole body instead of a 206.
            # Slice our window out of it rather than mis-aligning every subsequent read. Only a
            # whole-body reply is recoverable: `expected == self._size` implies `start == 0`, so
            # this branch is unambiguous about where our window sits.
            data = data[start : end + 1]
        elif len(data) != expected:
            # Anything else — a truncated reply, or a file that shrank since it was listed — cannot
            # be placed. Fail rather than cache a short block: a short block makes the next read
            # return zero bytes, which the BufferedReader above reads as EOF, and the profile comes
            # out quietly wrong instead of not at all.
            raise OSError(f"ranged read of bytes={start}-{end} returned {len(data)} bytes, expected {expected}")

        self._blocks[index] = data
        self._blocks.move_to_end(index)
        while len(self._blocks) > self._max_cached_blocks:
            self._blocks.popitem(last=False)
        return data


class FilesetFileSource:
    """Reads the files of a platform fileset without staging them on local disk.

    Satisfies the same two-method seam as
    :class:`~nemo_datasets_plugin.profiler.file_source.LocalFileSource`, so the profiler is
    unchanged by which one it is handed.
    """

    def __init__(
        self,
        client: FilesetClient,
        *,
        workspace: str,
        fileset: str,
        block_size: int = _DEFAULT_BLOCK_SIZE,
    ) -> None:
        self._client = client
        self._workspace = workspace
        self._fileset = fileset
        self._block_size = block_size
        self._sizes: dict[str, int] | None = None

    def list_files(self) -> list[FileEntry]:
        """Every file in the fileset, sorted by path."""
        response = self._client.list_files(workspace=self._workspace, name=self._fileset).data()
        entries = sorted(
            (FileEntry(path=file.path, size_bytes=file.size) for file in response.data),
            key=lambda entry: entry.path,
        )
        self._sizes = {entry.path: entry.size_bytes for entry in entries}
        return entries

    def open(self, path: str) -> BinaryIO:
        """A seekable, read-only stream over one file, served by ranged GETs.

        Wrapped in a :class:`io.BufferedReader` so line-oriented formats read sequentially without
        a call per line, while parquet keeps the random access it needs.
        """
        reader = _RangedFile(
            lambda start, end: self._fetch(path, start, end),
            self._size_of(path),
            block_size=self._block_size,
        )
        return io.BufferedReader(reader)

    def _size_of(self, path: str) -> int:
        if self._sizes is None:
            self.list_files()
        sizes = self._sizes or {}
        try:
            return sizes[path]
        except KeyError:
            raise FileNotFoundError(f"{path!r} is not a file of fileset {self._fileset!r}") from None

    def _fetch(self, path: str, start: int, end: int) -> bytes:
        response = self._client.with_headers({"Range": f"bytes={start}-{end}"}).download_file(
            workspace=self._workspace, name=self._fileset, path=path
        )
        return response.read()
