# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Developer entry point for the custom Gym environment workflow.

Run this file directly from the repository root. It parses the small public CLI,
loads optional environment overrides, obtains the NVIDIA API key, and delegates
the complete operation to ``CustomGymEnvironmentWorkflow``. The other Python
files in this directory are implementation modules and are not run directly.
"""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from config import Settings


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the single developer entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Artifact directory; defaults to a unique /tmp/nmp-gym-custom-environment-* path",
    )
    parser.add_argument(
        "--environment-dir",
        type=Path,
        help="Complete wheels-v1 environment directory; requires --dataset",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help="Gym JSONL dataset for --environment-dir",
    )
    parser.add_argument(
        "--resources-server",
        help="Resources server to run; inferred when the environment declares exactly one",
    )
    return parser


def _inference_api_key() -> str:
    """Read the inference API key from the environment or a hidden prompt."""
    configured_key = os.environ.get("INFERENCE_NVIDIA_API_KEY", "")
    if configured_key:
        return configured_key
    return getpass.getpass("NVIDIA Inference API key: ")


def main() -> int:
    """Parse configuration and execute the complete workflow once."""
    parser = _parser()
    arguments = parser.parse_args()
    if (arguments.environment_dir is None) != (arguments.dataset is None):
        parser.error("--environment-dir and --dataset must be supplied together")

    # Delay plugin-heavy imports so ``--help`` stays fast and side-effect free.
    from workflow import CustomGymEnvironmentWorkflow

    settings = Settings.from_environment(
        run_dir=arguments.run_dir,
        environment_dir=arguments.environment_dir,
        dataset=arguments.dataset,
        resources_server=arguments.resources_server,
    )
    workflow = CustomGymEnvironmentWorkflow(settings)
    workflow.run(inference_api_key=_inference_api_key())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
