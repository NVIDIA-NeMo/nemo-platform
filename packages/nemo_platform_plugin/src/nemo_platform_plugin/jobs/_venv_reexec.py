r"""Re-exec ``nemo <plugin> <job> run`` inside a caller-supplied venv.

This module implements the minimal ``--venv /path/to/venv`` affordance on
``run`` (AIRCORE-406): when the caller's Python interpreter doesn't have
compatible dependencies for the target plugin, re-run the same CLI inside
``<venv>/bin/python`` and stream stdio back. No new backends, no wire
changes — this is a client-side re-exec shim.

Surface:

- :func:`reexec_run_in_venv` — resolve the target interpreter, validate it
  has ``nemo_platform`` importable, strip ``--venv`` from *argv*, spawn
  the child with inherited stdio, return the child's exit code.
- :func:`strip_venv_flag` — drop ``--venv <path>`` / ``--venv=<path>``
  from an argv list. Pulled out so unit tests can pin the parsing shape
  without spawning subprocesses.

Design notes:

- Re-exec uses ``<venv>/bin/python -m nemo_platform.cli.app`` rather than
  ``<venv>/bin/nemo``. Both work when ``nemo-platform`` is installed, but
  ``-m`` sidesteps the "bin/nemo shebang points at the wrong interpreter"
  papercut that occurs with editable installs under certain venv layouts.
  The zippy demo (``rsadler/plugin-demo-zippy``) does the same thing.
- Stdio is inherited, not captured. Typer's ``echo`` output in the child
  streams straight through to the caller's terminal; no line buffering
  surprises, no log-capture games.
- ``subprocess.run`` with ``check=False``, not ``os.execv``. Slightly
  higher overhead (one extra fork) but much easier to test and preserves
  Typer's result reporting in the parent. Signal forwarding is fine for
  interactive use — Ctrl-C reaches the child through the shared pgroup.
- Windows (``Scripts\python.exe``) is not supported in this pass. Add
  when someone asks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def strip_venv_flag(argv: list[str]) -> list[str]:
    """Return *argv* with ``--venv <path>`` / ``--venv=<path>`` removed.

    Handles both forms; preserves the order of every other token. Does
    not touch ``argv[0]``; callers that want to drop the entry-point
    script path are expected to slice it off themselves.

    Example::

        strip_venv_flag(["nemo", "dd", "generate", "run",
                          "--venv", "/tmp/v", "--spec-file", "s.json"])
        # ["nemo", "dd", "generate", "run", "--spec-file", "s.json"]
    """
    out: list[str] = []
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--venv":
            # Drop the flag and its value.
            i += 2
            continue
        if token.startswith("--venv="):
            i += 1
            continue
        out.append(token)
        i += 1
    return out


def reexec_run_in_venv(venv: Path, argv: list[str]) -> int:
    """Re-run ``run`` inside *venv*'s Python, stream stdio, return exit code.

    Args:
        venv: Path to the target virtualenv (the directory containing
            ``bin/python``). Must already exist — auto-creation is
            deferred to a follow-up (``--create-venv``).
        argv: Original caller argv, typically ``sys.argv``. The entry-point
            script path at ``argv[0]`` is dropped before re-exec; the
            remaining tokens (minus ``--venv``) are passed verbatim.

    Returns:
        Exit code to propagate: ``0`` on success, ``1`` on helper-level
        errors (missing interpreter, ``nemo_platform`` not importable),
        or the child's returncode on successful spawn.

    Errors are reported to stderr with actionable messages; the caller
    is expected to surface the returned code via ``typer.Exit(code)``.
    """
    venv_python = venv / "bin" / "python"
    # is_file() + X_OK rejects directories, dangling symlinks, and
    # non-executable files — `exists()` alone lets all of those through and
    # then `subprocess.run` raises a confusing OSError.
    if not venv_python.is_file() or not os.access(venv_python, os.X_OK):
        print(
            f"Error: --venv {venv}: no executable python interpreter at {venv_python}",
            file=sys.stderr,
        )
        return 1

    # Validate the target venv has nemo-platform installed. Cheap check —
    # ~100ms per call — and it turns a confusing child-side traceback into
    # a one-line actionable error. Intentionally does not import the
    # plugin package: that error is strictly better surfaced by the child
    # (shows the real ImportError for the plugin).
    try:
        probe = subprocess.run(
            [str(venv_python), "-c", "import nemo_platform"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        print(
            f"Error: --venv {venv}: failed to spawn {venv_python}: {exc}",
            file=sys.stderr,
        )
        return 1
    if probe.returncode != 0:
        print(
            f"Error: --venv {venv}: target venv does not have nemo-platform installed.\n"
            f"Install it with: uv pip install --python {venv_python} nemo-platform",
            file=sys.stderr,
        )
        return 1

    # Drop argv[0] (the `nemo` script path) — we re-enter via -m.
    child_args = strip_venv_flag(argv[1:])
    cmd = [str(venv_python), "-m", "nemo_platform.cli.app", *child_args]
    # No stdio redirection: inherit the parent's fds so the child's output
    # streams through unbuffered and signals reach it naturally.
    try:
        result = subprocess.run(cmd, check=False)
    except OSError as exc:
        print(
            f"Error: --venv {venv}: failed to spawn child: {exc}",
            file=sys.stderr,
        )
        return 1
    return result.returncode
