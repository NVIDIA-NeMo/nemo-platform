# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Opt-in E2E coverage for host-local Safe Synthesizer execution.

This test intentionally bypasses Docker and the platform Jobs service. It runs
the plugin CLI against the host Python/CUDA environment, so it is skipped unless
RUN_NSS_LOCAL_E2E=1 is set.
"""

from __future__ import annotations

import csv
import json
import os
import random
import subprocess
from datetime import date
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.gpu_integration,
    pytest.mark.slow,
]


FLAVORS = [
    "Vanilla",
    "Chocolate",
    "Strawberry",
    "Mint Chocolate Chip",
    "Cookies and Cream",
    "Pistachio",
    "Rocky Road",
    "Butter Pecan",
    "Coffee",
    "Mango Sorbet",
    "Salted Caramel",
    "Cookie Dough",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _write_faker_csv(path: Path, rows: int = 10000) -> None:
    faker = pytest.importorskip("faker")
    fake = faker.Faker()
    faker.Faker.seed(42)
    random.seed(42)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["name", "signup_date", "birthdate", "favorite_ice_cream_flavor"],
        )
        writer.writeheader()
        for _ in range(rows):
            writer.writerow(
                {
                    "name": fake.name(),
                    "signup_date": fake.date_between_dates(
                        date_start=date(2020, 1, 1),
                        date_end=date(2026, 5, 4),
                    ).isoformat(),
                    "birthdate": fake.date_between_dates(
                        date_start=date(1945, 1, 1),
                        date_end=date(2006, 12, 31),
                    ).isoformat(),
                    "favorite_ice_cream_flavor": random.choice(FLAVORS),
                }
            )


def _write_synthesis_spec(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "data_source": "default/local-input#input.csv",
                "config": {
                    "enable_synthesis": True,
                    "enable_replace_pii": False,
                    "generation": {
                        "num_records": 100,
                    },
                    "evaluation": {
                        "enabled": True,
                    },
                    "privacy": {
                        "dp_enabled": False,
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_local_synthesis_cli_generates_data(tmp_path: Path) -> None:
    if os.environ.get("RUN_NSS_LOCAL_E2E") != "1":
        pytest.skip("Set RUN_NSS_LOCAL_E2E=1 to run host-local NSS synthesis E2E")

    input_csv = tmp_path / "input.csv"
    spec_file = tmp_path / "nss-job-synthesis.json"
    output_dir = tmp_path / "nss-output"
    _write_faker_csv(input_csv)
    _write_synthesis_spec(spec_file)

    command = [
        "uv",
        "run",
        "nemo",
        "safe-synthesizer",
        "run-local",
        "--workspace",
        "default",
        "--spec-file",
        str(spec_file),
        "--data-source",
        str(input_csv),
        "--output-dir",
        str(output_dir),
    ]
    print("Running:", " ".join(command), flush=True)

    result = subprocess.run(
        command,
        cwd=_repo_root(),
        timeout=int(os.environ.get("NSS_LOCAL_E2E_TIMEOUT_SECONDS", "3600")),
        check=False,
    )
    assert result.returncode == 0

    synthetic_data = output_dir / "synthetic-data.csv"
    summary_file = output_dir / "summary.json"
    assert synthetic_data.exists()
    assert summary_file.exists()

    with synthetic_data.open(encoding="utf-8") as f:
        row_count = sum(1 for _ in f) - 1
    assert row_count == 100

    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    timing = summary["timing"]
    assert timing["training_time_sec"] is not None
    assert timing["generation_time_sec"] is not None
