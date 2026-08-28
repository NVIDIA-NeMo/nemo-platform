#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Eval Author walkthrough quick-start CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_CLI_DIR = Path(__file__).resolve().parent
if str(_CLI_DIR) not in sys.path:
    sys.path.insert(0, str(_CLI_DIR))

from display import get_profile  # noqa: E402
from interrupts import WalkthroughInterrupted, interrupt_message  # noqa: E402
from run_report import WalkthroughGapFailures  # noqa: E402
from runner import (  # noqa: E402
    DEFAULT_WORKSPACE,
    WalkthroughArtifactsKept,
    WalkthroughConfig,
    WalkthroughError,
    run_walkthrough,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eval-author-walkthrough",
        description=(
            "Prepare the rho-agent walkthrough workspace, launch a coding agent, "
            "and watch Eval Author artifacts with Rich output."
        ),
    )
    parser.add_argument(
        "--agent",
        required=True,
        choices=("cursor", "claude"),
        help="Branding and CLI backend for the coding agent (Cursor Agent or Claude Code).",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        help=f"Walkthrough workspace directory (default: {DEFAULT_WORKSPACE}).",
    )
    return parser


def _wait_for_enter(*, message: str = "Press ENTER to exit.") -> None:
    """Hold the terminal open after the live display closes so results can be read."""
    if not sys.stdin.isatty():
        return
    try:
        input(f"\n{message}")
    except EOFError:
        return


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        profile = get_profile(args.agent)
    except ValueError as exc:
        parser.error(str(exc))

    workspace_input = args.workspace if args.workspace is not None else DEFAULT_WORKSPACE
    workspace = workspace_input.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        workspace_label = str(workspace.relative_to(Path.cwd()))
    except ValueError:
        workspace_label = str(workspace_input)

    config = WalkthroughConfig(
        workspace=workspace,
        workspace_label=workspace_label,
        profile=profile,
    )

    try:
        run_walkthrough(config)
    except WalkthroughInterrupted as exc:
        print(interrupt_message(phase=exc.phase), file=sys.stderr)
        return 130
    except KeyboardInterrupt:
        print(interrupt_message(), file=sys.stderr)
        return 130
    except WalkthroughArtifactsKept as exc:
        print(str(exc), file=sys.stderr)
        return 0
    except WalkthroughGapFailures:
        return 1
    except WalkthroughError as exc:
        print(f"walkthrough failed: {exc}", file=sys.stderr)
        _wait_for_enter()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
