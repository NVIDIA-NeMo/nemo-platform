# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Immutable inventory tests for existing Eval Author reference task sets."""

import json
import shutil
from pathlib import Path

import pytest
from nemo_eval_author_plugin.eval_author.inventory import (
    ReferenceTaskSetInventory,
    build_reference_task_set_inventory,
)
from nemo_eval_author_plugin.eval_author.models import EvalAuthorEvaluationContext
from nemo_experimentalist_plugin.entities import DatasetRef
from pydantic import ValidationError


def _write_task(
    dataset_dir: Path,
    task_id: str,
    *,
    instruction: str = "Consult inventory before answering.\n",
    source_trace_ref: str | None = None,
    source_insight_id: str = "insight-source",
    metric_key: str = "quality",
    declared_metric_key: str | None = None,
    verifier_suffix: str = "",
    metadata_values: str = "",
    extra_toml: str = "",
) -> None:
    task_dir = dataset_dir / task_id
    tests_dir = task_dir / "tests"
    environment_dir = task_dir / "environment"
    tests_dir.mkdir(parents=True)
    environment_dir.mkdir()
    provenance = (
        "\n[metadata.nemo_experimentalist]\n"
        f'source_trace_ref = "{source_trace_ref}"\n'
        f'insight_id = "{source_insight_id}"\n'
        if source_trace_ref is not None
        else ""
    )
    metric_contract = (
        f"""
[metadata.nemo_eval_author.metric_contract]
metrics = [
  {{ key = "{declared_metric_key}", description = "Declared metric {declared_metric_key}.", runtime_evidence = ["OTLP tool spans"], scale = "unit_interval", direction = "higher_is_better" }},
]
"""
        if declared_metric_key is not None
        else ""
    )
    (task_dir / "task.toml").write_text(
        f"""\
# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
version = "1.0"

[task]
name = "local/{task_id}"

[verifier]
timeout_sec = 60.0

[environment]
build_timeout_sec = 60.0
cpus = 1
memory_mb = 512
storage_mb = 1024
gpus = 0
network_mode = "no-network"
mcp_servers = []

[metadata]
{metadata_values}
{provenance}
{metric_contract}
{extra_toml}
""",
        encoding="utf-8",
    )
    (task_dir / "instruction.md").write_text(instruction, encoding="utf-8")
    (environment_dir / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    (tests_dir / "test.sh").write_text(
        f"""\
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /logs/verifier
printf '{{"reward": 1.0, "{metric_key}": 0.5}}\\n' > /logs/verifier/reward.json
{verifier_suffix}
""",
        encoding="utf-8",
    )


def _inventory(dataset_dir: Path, *, split: str = "train") -> ReferenceTaskSetInventory:
    return build_reference_task_set_inventory(
        (
            DatasetRef(
                uri=dataset_dir.as_uri(),
                metadata={"id": f"{split}-dataset", "split": split},
            ),
        )
    )


def test_inventory_identity_is_stable_when_dataset_directory_is_copied(tmp_path: Path) -> None:
    source = tmp_path / "source" / "benchmark"
    copied = tmp_path / "elsewhere" / "renamed-benchmark"
    _write_task(source, "task-a", source_trace_ref="trace-a")
    _write_task(source, "task-b", instruction="A distinct scenario.\n", source_trace_ref="trace-b")
    copied.parent.mkdir(parents=True)
    shutil.copytree(source, copied)

    original = _inventory(source, split="train")
    relocated = _inventory(copied, split="validation")

    assert relocated == original
    assert relocated.identity == original.identity
    serialized = json.dumps(original.model_dump(mode="json"), sort_keys=True)
    assert str(source) not in serialized
    assert str(copied) not in serialized


def test_inventory_represents_duplicate_fingerprints_and_trace_provenance(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(dataset_dir, "task-a", source_trace_ref="shared-trace")
    _write_task(dataset_dir, "task-b", source_trace_ref="shared-trace")

    inventory = _inventory(dataset_dir)

    assert [task.task_id for task in inventory.tasks] == ["task-a", "task-b"]
    assert inventory.tasks[0].fingerprint == inventory.tasks[1].fingerprint
    assert inventory.tasks[0].source_trace_refs == ("shared-trace",)
    assert inventory.tasks[1].source_trace_refs == ("shared-trace",)
    assert [(group.value, group.task_ids) for group in inventory.duplicate_fingerprints] == [
        (inventory.tasks[0].fingerprint, ("task-a", "task-b")),
    ]
    assert [(group.value, group.task_ids) for group in inventory.duplicate_provenance] == [
        ("shared-trace", ("task-a", "task-b")),
    ]


def test_inventory_deduplicates_verifier_families_and_keeps_representative_layout(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(dataset_dir, "task-a", source_trace_ref="trace-a")
    _write_task(dataset_dir, "task-b", instruction="Another scenario.\n", source_trace_ref="trace-b")
    _write_task(
        dataset_dir,
        "task-c",
        instruction="A third scenario.\n",
        source_trace_ref="trace-c",
        verifier_suffix="echo changed >/dev/null\n",
    )

    inventory = _inventory(dataset_dir)

    assert len(inventory.verifier_families) == 2
    shared_family = next(family for family in inventory.verifier_families if len(family.task_ids) == 2)
    assert shared_family.task_ids == ("task-a", "task-b")
    assert shared_family.representative_task_id == "task-a"
    assert shared_family.layout.directory == "tests"
    assert shared_family.layout.entrypoint == "test.sh"
    assert [file.path for file in shared_family.layout.files] == ["test.sh"]
    assert shared_family.layout.files[0].content_encoding == "utf-8"
    assert "/benchmark/" not in shared_family.layout.files[0].path


def test_inventory_exposes_existing_metric_keys_and_contracts(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(
        dataset_dir,
        "task-a",
        metric_key="inventory_grounding",
        declared_metric_key="inventory_grounding",
    )

    inventory = _inventory(dataset_dir)

    assert inventory.metric_keys == ("inventory_grounding",)
    assert tuple(contract.key for contract in inventory.metric_contracts) == inventory.metric_keys
    assert inventory.metric_contracts[0].description == "Declared metric inventory_grounding."
    assert inventory.metric_contracts[0].runtime_evidence == ("OTLP tool spans",)
    assert inventory.metric_contracts[0].scale == "unit_interval"
    assert inventory.metric_contracts[0].direction == "higher_is_better"
    assert inventory.tasks[0].metric_keys == inventory.metric_keys
    assert inventory.verifier_families[0].metric_keys == inventory.metric_keys


def test_inventory_consumes_explicit_dataset_reference_metric_contract(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(dataset_dir, "task-a", metric_key="dataset_declared")
    reference = DatasetRef(
        uri=dataset_dir.as_uri(),
        metadata={
            "metric_contract": {
                "metrics": [
                    {
                        "key": "dataset_declared",
                        "description": "Declared once for this reference task set.",
                        "runtime_evidence": ["Current-run artifact"],
                        "scale": "unit_interval",
                        "direction": "higher_is_better",
                    }
                ]
            }
        },
    )

    context = EvalAuthorEvaluationContext(
        task_template=DatasetRef(uri="file:///template"),
        reference_task_sets=(reference,),
    )
    inventory = build_reference_task_set_inventory(context.reference_task_sets)

    assert inventory.metric_keys == ("dataset_declared",)
    assert inventory.metric_contracts[0].description == "Declared once for this reference task set."
    assert inventory.tasks[0].metric_keys == ("dataset_declared",)


def test_inventory_does_not_infer_metrics_from_unrelated_source_dicts(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(
        dataset_dir,
        "task-a",
        metric_key="undeclared_dynamic_metric",
        verifier_suffix="""\
python - <<'PY'
unrelated = {"looks_like_a_metric": 0.5}
print(unrelated)
PY
""",
    )

    inventory = _inventory(dataset_dir)

    assert inventory.metric_keys == ()
    assert inventory.metric_contracts == ()
    assert inventory.tasks[0].metric_keys == ()
    assert inventory.verifier_families[0].metric_keys == ()


def test_inventory_rejects_symlink_that_escapes_reference_root(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    outside_dataset = tmp_path / "outside"
    _write_task(outside_dataset, "task-a")
    dataset_dir.mkdir()
    (dataset_dir / "task-a").symlink_to(outside_dataset / "task-a", target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        _inventory(dataset_dir)


def test_inventory_rejects_internal_runtime_symlink(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(dataset_dir, "task-a")
    environment = dataset_dir / "task-a" / "environment"
    (environment / "dockerfile-link").symlink_to(environment / "Dockerfile")

    with pytest.raises(ValueError, match="symbolic link"):
        _inventory(dataset_dir)


def test_fingerprint_normalizes_only_declared_eval_author_provenance(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(
        dataset_dir,
        "task-a",
        source_trace_ref="trace-a",
        source_insight_id="insight-a",
    )
    _write_task(
        dataset_dir,
        "task-b",
        source_trace_ref="trace-b",
        source_insight_id="insight-b",
    )

    inventory = _inventory(dataset_dir)

    assert inventory.tasks[0].fingerprint == inventory.tasks[1].fingerprint
    assert inventory.tasks[0].source_trace_refs == ("trace-a",)
    assert inventory.tasks[1].source_trace_refs == ("trace-b",)


@pytest.mark.parametrize(
    "semantic_table",
    [
        "task.semantic",
        "environment.semantic",
        "metadata.domain.nested",
    ],
)
def test_fingerprint_preserves_semantic_fields_named_trace_or_insight_id(
    tmp_path: Path,
    semantic_table: str,
) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(
        dataset_dir,
        "task-a",
        source_trace_ref="same-declared-trace",
        extra_toml=(
            f"[{semantic_table}]\n"
            'trace_id = "business-trace-a"\n'
            'insight_id = "business-insight-a"\n'
            'nested = [[{ trace_id = "nested-trace-a", insight_id = "nested-insight-a" }]]'
        ),
    )
    _write_task(
        dataset_dir,
        "task-b",
        source_trace_ref="same-declared-trace",
        extra_toml=(
            f"[{semantic_table}]\n"
            'trace_id = "business-trace-b"\n'
            'insight_id = "business-insight-b"\n'
            'nested = [[{ trace_id = "nested-trace-b", insight_id = "nested-insight-b" }]]'
        ),
    )

    inventory = _inventory(dataset_dir)

    assert inventory.tasks[0].fingerprint != inventory.tasks[1].fingerprint
    assert inventory.tasks[0].source_trace_refs == ("same-declared-trace",)
    assert inventory.tasks[1].source_trace_refs == ("same-declared-trace",)


def test_inventory_canonicalizes_toml_temporal_values(tmp_path: Path) -> None:
    source = tmp_path / "source"
    copied = tmp_path / "copied"
    _write_task(
        source,
        "task-a",
        metadata_values=(
            "calendar_date = 2026-08-05\nlocal_time = 15:34:12.123456\nobserved_at = 2026-08-05T15:34:12.123456Z"
        ),
    )
    shutil.copytree(source, copied)

    original = _inventory(source)
    relocated = _inventory(copied)

    assert original == relocated
    assert original.identity == relocated.identity
    assert original.tasks[0].fingerprint == relocated.tasks[0].fingerprint


def test_typed_canonicalization_separates_date_from_lookalike_table(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(
        dataset_dir,
        "task-date",
        metadata_values="temporal = 2026-08-05",
    )
    _write_task(
        dataset_dir,
        "task-table",
        extra_toml='[metadata.temporal]\n"$toml_date" = "2026-08-05"',
    )

    inventory = _inventory(dataset_dir)

    assert inventory.tasks[0].fingerprint != inventory.tasks[1].fingerprint


def test_inventory_models_are_frozen_and_do_not_expose_source_datasets(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "benchmark"
    _write_task(dataset_dir, "task-a")

    inventory = _inventory(dataset_dir)

    assert isinstance(inventory.tasks, tuple)
    assert "dataset" not in type(inventory).model_fields
    assert "source_dataset" not in type(inventory.tasks[0]).model_fields
    with pytest.raises(ValidationError, match="frozen"):
        inventory.identity = "sha256:changed"  # type: ignore[misc]
