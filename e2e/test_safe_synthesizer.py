"""Opt-in container E2E for Safe Synthesizer GPU jobs (Docker or Kubernetes).

These tests exercise the full platform path: plugin job API -> Jobs controller ->
GPU container step -> safe-synthesizer-tasks image -> Files results.

Excluded from default kind-cpu CI (no GPU, no safe-synthesizer-tasks image).
Run manually against minikube GPU, dev-blue, or a GPU-enabled Docker backend:

    # After nss-k8s-deploy.sh (or MINIKUBE_GPU=1 BUILD_SAFE_SYNTHESIZER=1 local_build_and_upgrade.sh)
    NMP_BASE_URL=http://localhost:30080 \
      uv run --frozen pytest e2e/test_safe_synthesizer.py -v --run-e2e --run-slow --feature gpu
"""

from __future__ import annotations

import os
import random
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from nemo_platform import NeMoPlatform
from nemo_safe_synthesizer_plugin.sdk.job import SafeSynthesizerJob
from nemo_safe_synthesizer_plugin.sdk.job_builder import SafeSynthesizerJobBuilder

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SETUP_MODEL_FILESETS = _REPO_ROOT / "plugins/nemo-safe-synthesizer/scripts/setup_model_filesets.py"

_MIN_INPUT_ROWS = 200
_DEFAULT_INPUT_ROWS = 250
_DEFAULT_NUM_RECORDS = _DEFAULT_INPUT_ROWS

_ICE_CREAM_FLAVORS = [
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

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.container_only,
    pytest.mark.requires_gpu,
    pytest.mark.slow,
    pytest.mark.timeout(7200),
]


@pytest.fixture(scope="module")
def nss_model_filesets(sdk: NeMoPlatform, _services: str) -> None:
    """Register HuggingFace-backed model filesets required by Safe Synthesizer tasks."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(_SETUP_MODEL_FILESETS),
            "--files-api-url",
            _services,
        ],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"Failed to register Safe Synthesizer model filesets\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _synthesis_dataset(rows: int | None = None) -> pd.DataFrame:
    """Build a tabular dataset suitable for Safe Synthesizer training (>= 200 rows).

    Schema matches plugins/nemo-safe-synthesizer/tests/e2e/test_local_synthesis.py:
    names, dates, and a categorical column with realistic variation.
    """
    if rows is None:
        rows = int(os.environ.get("NSS_E2E_INPUT_ROWS", str(_DEFAULT_INPUT_ROWS)))
    if rows < _MIN_INPUT_ROWS:
        raise ValueError(f"Safe Synthesizer container E2E requires at least {_MIN_INPUT_ROWS} input rows, got {rows}")

    faker_mod = pytest.importorskip("faker")
    fake = faker_mod.Faker()
    faker_mod.Faker.seed(42)
    random.seed(42)

    records = [
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
            "favorite_ice_cream_flavor": random.choice(_ICE_CREAM_FLAVORS),
        }
        for _ in range(rows)
    ]
    return pd.DataFrame.from_records(records)


def test_safe_synthesizer_container_job_completes(
    sdk: NeMoPlatform,
    workspace: str,
    nss_model_filesets: None,
) -> None:
    """Submit a GPU container job and verify synthetic data is produced."""
    num_records = int(os.environ.get("NSS_E2E_NUM_RECORDS", str(_DEFAULT_NUM_RECORDS)))
    if num_records < _MIN_INPUT_ROWS:
        raise ValueError(f"NSS_E2E_NUM_RECORDS must be at least {_MIN_INPUT_ROWS}, got {num_records}")

    job = (
        SafeSynthesizerJobBuilder(sdk, workspace=workspace)
        .with_data_source(_synthesis_dataset())
        .synthesize()
        .with_generate(num_records=num_records)
        .with_evaluate(enabled=True)
        .create_job()
    )

    nss_job = SafeSynthesizerJob(job.job_name, sdk, workspace=workspace)
    nss_job.wait_for_completion(poll_interval=15, verbose=True)

    summary = nss_job.fetch_summary()
    assert summary.timing.training_time_sec is not None
    assert summary.timing.generation_time_sec is not None

    synthetic = nss_job.fetch_data()
    assert len(synthetic) == num_records
