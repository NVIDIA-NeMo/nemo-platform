# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from scaled_evals.api.auth import CurrentPrincipal
from scaled_evals.api.routers.benchmark_imports import publish_benchmark_import
from scaled_evals.api.schemas.benchmark_imports import BenchmarkImportCreate
from scaled_evals.benchmark_import import (
    import_id_from_legacy_state,
    load_import_images,
    write_legacy_import_state,
)


def test_import_schema_and_compatibility_state_preserve_portable_metadata(tmp_path: Path) -> None:
    request = BenchmarkImportCreate.model_validate(
        {
            "manifest_sha256": "a" * 64,
            "manifest": {
                "schema_version": 1,
                "catalog_id": "fixture",
                "visibility": "public",
                "source": {"type": "git", "commit": "b" * 40},
                "tasks": [
                    {
                        "name": "Task",
                        "slug": "task",
                        "pack": "packs/task.tar.gz",
                        "pack_sha256": "c" * 64,
                    }
                ],
                "benchmarks": [{"name": "Bench", "slug": "bench", "tasks": ["task"]}],
            },
        }
    )
    assert request.visibility == "public"

    images_path = tmp_path / "images.jsonl"
    images_path.write_text(
        json.dumps(
            {
                "slug": "task",
                "status": "ready",
                "image_ref": "registry.example/task:one",
                "image_digest": "sha256:" + "d" * 64,
                "source_commit": "abc",
            }
        )
        + "\n"
    )
    images = load_import_images([images_path])
    assert images["task"]["source_commit"] == "abc"

    state_path = tmp_path / "state.json"
    write_legacy_import_state(
        state_path,
        {
            "id": "bmi_one",
            "tasks": [
                {
                    "slug": "task",
                    "task_id": "task_1",
                    "task_revision": 2,
                    "status": "ready",
                    "image_ref": images["task"]["image_ref"],
                    "image_digest": images["task"]["image_digest"],
                    "image_metadata": {"source_commit": images["task"]["source_commit"]},
                }
            ],
        },
        phase="finalize",
    )
    assert import_id_from_legacy_state(state_path) == "bmi_one"
    assert json.loads(state_path.read_text())[0]["source_commit"] == "abc"


def test_publish_rejects_benchmark_slug_owned_by_another_principal() -> None:
    db = MagicMock()
    db.benchmark_imports.get.return_value = {
        "id": "bmi_one",
        "manifest": {"benchmarks": [{"slug": "bench"}]},
        "visibility": "public",
    }
    db.benchmark_imports.tasks.return_value = [
        {
            "slug": "task",
            "status": "ready",
            "task_id": "task_one",
            "task_revision": 1,
        }
    ]
    db.benchmark_imports.benchmarks.return_value = [{"slug": "bench", "name": "Bench", "task_slugs": ["task"]}]
    db.benchmarks.get_by_slug.return_value = {
        "id": "bm_other",
        "owner_id": "other",
    }

    with pytest.raises(HTTPException) as exc_info:
        publish_benchmark_import(
            "bmi_one",
            db,
            CurrentPrincipal(owner_type="USER", owner_id="owner"),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error"]["code"] == "benchmark_slug_owned_by_another_user"
    db.benchmarks.update.assert_not_called()
    db.benchmarks.create_next_revision.assert_not_called()
