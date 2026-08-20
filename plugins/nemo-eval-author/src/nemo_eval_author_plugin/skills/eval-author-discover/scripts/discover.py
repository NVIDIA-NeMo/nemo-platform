#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Record whether a repository's Harbor evaluations are ready to run.

Discovery exists so a later, cheaper model can run a repository's Harbor evals
without re-deriving how. That only works when every recorded fact was proved
rather than observed, so this command finds the repository's Harbor artifacts and
then makes Harbor's own validators judge them.

Three phases, in order:

1. **Probe.** Standard library only. Is Harbor importable, and is its CLI on PATH?
2. **Inventory.** Standard library only. Which config files, dataset directories,
   and task directories does the repository own?
3. **Judge.** Only when Harbor is importable. Run the full validation ladder:
   schema, job resolution, agent, environment backend, CLI round trip, per-task
   validity, dropped-task coverage, and required host variables.

All three phases are provider-specific and live under ``providers/harbor/``. This
module owns only the parts no provider changes: argument parsing, phase order,
report assembly, and the exit code.

Without Harbor, phase 3 cannot run and no claim about runnability is possible.
The report is still emitted, every finding is marked ``"proven": false``, and the
verdict is a required failure naming what to install. An unproven inventory is
useful for orienting in an unfamiliar repository; it is never evidence.

This skill carries no dependency of its own. Harbor is the one import beyond the
standard library, and a repository holding Harbor evaluations has Harbor by
construction. PyYAML, pydantic, and toml arrive with it.

Usage:
    discover.py [--repo PATH] [--compact]

    --repo PATH    Repository to inspect. Defaults to the working directory.
    --compact      Emit single-line JSON.

Prints a JSON report on stdout and writes nothing. ``SKILL.md`` tells the agent
where to save it.

Exit codes:
    0  every repository-owned config passed every required check
    1  a required check failed, Harbor is unavailable, or the path is unusable

WARNING: Run this only against a trusted repository. Validating an agent's
import path executes module top-level code.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Every bundled module resolves against this directory, so put it on the path
# before importing one. Note that it holds no directory named after a provider
# package: a `harbor/` directory here would satisfy `find_spec("harbor")` on a
# machine without Harbor and make the probe claim an install that is not there.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _checks import CheckResult, required_failures  # noqa: E402
from providers.harbor import _probe  # noqa: E402
from providers.harbor._inventory import RepositoryScan, scan_repository  # noqa: E402

_SCHEMA_VERSION = 1
_MIN_PYTHON = (3, 11)


def _unproven(checks: list[CheckResult]) -> list[CheckResult]:
    """Mark observed findings so they cannot read as evidence."""
    for result in checks:
        result.proven = False
    return checks


async def _judge(scan: RepositoryScan, repo_root: Path) -> list[dict]:
    """Run the validation ladder against each config Harbor can read.

    Imported here rather than at module scope because the ladder imports Harbor,
    which a repository without Harbor does not have.
    """
    from providers.harbor import _ladder

    configs: list[dict] = []
    for candidate in scan.configs:
        outcome = await _ladder.run_ladder(candidate, repo_root)
        configs.append(
            {
                "name": candidate.name,
                "path": _display(candidate.path, repo_root),
                "runnable": not required_failures(outcome.checks),
                "required_env_vars": [
                    {
                        "name": item.name,
                        "default": item.default,
                        "declared_in": _display(item.declared_in, repo_root),
                    }
                    for item in outcome.required_env_vars
                ],
                "checks": [result.as_dict() for result in outcome.checks],
                "_checks": outcome.checks,
            }
        )
    return configs


def _unjudged(scan: RepositoryScan, repo_root: Path) -> list[dict]:
    """Describe each config without claiming anything about it."""
    return [
        {
            "name": candidate.name,
            "path": _display(candidate.path, repo_root),
            "runnable": False,
            "required_env_vars": [],
            "checks": [],
            "_checks": [],
        }
        for candidate in scan.configs
    ]


def _display(path: Path, repo_root: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _run_command(repo_root: Path, configs: list[dict]) -> str | None:
    """Return the Harbor command, only when exactly one config is runnable."""
    runnable = [config for config in configs if config["runnable"]]
    if len(configs) != 1 or len(runnable) != 1:
        return None
    return "cd {} && harbor job start -c {}".format(repo_root, runnable[0]["path"])


def _fail(message: str, hint: str) -> int:
    json.dump({"error": message, "hint": hint}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 1


async def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record whether a repository's Harbor evaluations are ready to run.")
    parser.add_argument("--repo", type=Path, default=Path(), help="Repository to inspect.")
    parser.add_argument("--compact", action="store_true", help="Emit single-line JSON.")
    args = parser.parse_args(argv)

    if sys.version_info < _MIN_PYTHON:
        return _fail(
            "Discovery needs Python {}.{} or later; this is {}.".format(
                _MIN_PYTHON[0], _MIN_PYTHON[1], ".".join(str(part) for part in sys.version_info[:3])
            ),
            "Re-run with a newer interpreter, for example `python3.12 discover.py --repo .`.",
        )

    repo_root = args.repo.expanduser()
    if not repo_root.is_dir():
        return _fail(
            "Not a directory: {}".format(repo_root),
            "Pass the repository that holds your Harbor configs and task directories.",
        )
    repo_root = repo_root.resolve()

    runtime = _probe.probe()
    runtime_checks = _probe.probe_checks(runtime)
    scan = scan_repository(repo_root)
    proven = _probe.is_available(runtime)
    configs = await _judge(scan, repo_root) if proven else _unjudged(scan, repo_root)

    repository_checks = scan.checks if proven else _unproven(scan.checks)
    grouped = [*runtime_checks, *repository_checks, *(item for config in configs for item in config["_checks"])]
    for config in configs:
        config.pop("_checks")

    runnable = proven and bool(configs) and all(config["runnable"] for config in configs)
    report = {
        "schema_version": _SCHEMA_VERSION,
        "repo_root": repo_root.as_posix(),
        "provider": _probe.PROVIDER,
        "proven": proven,
        "runnable": runnable,
        "runtime": runtime,
        "configs": configs,
        "dataset_paths": [_display(path, repo_root) for path in scan.dataset_paths],
        "task_count": len(scan.task_paths),
        "ethos_path": scan.ethos_path,
        "fingerprint": "sha256:{}".format(scan.fingerprint),
        "input_file_count": scan.input_file_count,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
        "checks": [result.as_dict() for result in grouped],
    }
    report["run_command"] = _run_command(repo_root, configs)

    json.dump(report, sys.stdout, indent=None if args.compact else 2)
    sys.stdout.write("\n")
    return 0 if runnable else 1


def main(argv: list[str] | None = None) -> int:
    """Run discovery and print the JSON report."""
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    sys.exit(main())
