# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""CLI: ``sandboxed-gym serve ...``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from sandboxed_gym.serve import serve
from sandboxed_gym.serve_config import SandboxedGymServeConfig


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sandboxed-gym")
    sub = parser.add_subparsers(dest="command", required=True)

    serve_p = sub.add_parser(
        "serve",
        help="Start episode broker + Gym host (orchestrator or host-urls mode)",
    )
    serve_p.add_argument(
        "--config",
        "-c",
        type=Path,
        required=True,
        help="YAML/JSON serve config path",
    )
    serve_p.add_argument(
        "--mode",
        choices=("orchestrator", "host-urls"),
        default=None,
        help="Override serve_mode from config (default: orchestrator)",
    )
    serve_p.add_argument(
        "--bind",
        default="0.0.0.0:8090",
        help="Orchestrator proxy bind address (mode=orchestrator)",
    )
    serve_p.add_argument(
        "--session-file",
        type=Path,
        default=None,
        help="Write SandboxedGymSessionDescriptor JSON for cross-job handoff",
    )
    serve_p.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.command == "serve":
        raw = yaml.safe_load(args.config.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            parser.error("config root must be a mapping")
        cfg = SandboxedGymServeConfig.model_validate(raw)
        serve(
            cfg,
            mode=args.mode,
            bind=args.bind,
            session_file=args.session_file,
        )
        return 0

    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
