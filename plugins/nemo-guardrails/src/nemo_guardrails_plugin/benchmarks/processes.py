# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Process supervision for the benchmark harness.

Each child runs in its own session/process group so termination cleans up forked
worker processes (notably ``uvicorn --workers N`` and ``nemo services run``).
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Iterator

import httpx

log = logging.getLogger(__name__)

_TERMINATE_TIMEOUT_SECONDS = 20


@dataclass
class SupervisedProcess:
    """A long-lived child managed as a context manager.

    Stdout and stderr are merged into a single log file. The child is placed in a
    new session via ``start_new_session=True`` so ``os.killpg`` reaps any workers
    it forks.
    """

    name: str
    cmd: list[str]
    log_path: Path
    cwd: Path
    env: dict[str, str] | None = None
    _proc: subprocess.Popen[bytes] | None = field(default=None, init=False, repr=False)
    _log_fh: IO[bytes] | None = field(default=None, init=False, repr=False)

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc else None

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError(f"Process {self.name!r} already started")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_fh = self.log_path.open("wb")

        merged_env = {**os.environ, **(self.env or {})}
        log.info("Starting %s; log=%s", self.name, self.log_path)
        self._proc = subprocess.Popen(  # noqa: S603 - command is constructed internally
            self.cmd,
            cwd=str(self.cwd),
            env=merged_env,
            stdout=self._log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    def stop(self) -> None:
        proc = self._proc
        if proc is None:
            return
        if proc.poll() is not None:
            self._close_log()
            return

        try:
            pgid = os.getpgid(proc.pid)
        except ProcessLookupError:
            self._close_log()
            return

        log.info("Stopping %s pid=%d (pgid=%d)", self.name, proc.pid, pgid)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            self._close_log()
            return

        try:
            proc.wait(timeout=_TERMINATE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            log.warning(
                "%s did not exit after %ds; sending SIGKILL",
                self.name,
                _TERMINATE_TIMEOUT_SECONDS,
            )
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()

        self._close_log()

    def _close_log(self) -> None:
        if self._log_fh is not None:
            self._log_fh.close()
            self._log_fh = None

    def __enter__(self) -> "SupervisedProcess":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


@contextmanager
def supervised_processes(specs: list[SupervisedProcess]) -> Iterator[list[SupervisedProcess]]:
    """Enter every process spec in order; stop them in reverse on exit."""
    with ExitStack() as stack:
        for spec in specs:
            stack.enter_context(spec)
        yield specs


def write_pids_file(pids_file: Path, processes: list[SupervisedProcess]) -> None:
    pids_file.parent.mkdir(parents=True, exist_ok=True)
    with pids_file.open("w", encoding="utf-8") as f:
        for p in processes:
            if p.pid is not None:
                f.write(f"{p.name}:{p.pid}\n")


def wait_http(url: str, *, timeout_seconds: float, label: str, poll_interval: float = 1.0) -> None:
    """Poll ``url`` until it returns 2xx or ``timeout_seconds`` elapses."""
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5.0)
            if r.status_code < 400:
                return
            last_error = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(poll_interval)
    raise TimeoutError(f"Timed out waiting for {label} at {url}: {last_error}")
