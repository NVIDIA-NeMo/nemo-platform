# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Host-side preparation of trusted Harbor inputs before OpenShell launches."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from nemo_experimentalist_plugin.harbor_bridge.envelopes import register_dataset_envelope
from nemo_experimentalist_plugin.resolve import EffectiveExperimentPlan, resolve_dataset


@dataclass(frozen=True, slots=True)
class PreparedTrustedInputs:
    """Host-owned catalog paths that are also uploaded read-only-by-copy to OpenShell."""

    catalog_root: Path
    train_dataset: Path
    validation_dataset: Path
    task_template: Path | None


async def prepare_trusted_inputs(
    plan: EffectiveExperimentPlan,
    *,
    workspace: Path,
) -> PreparedTrustedInputs:
    """Resolve and snapshot the run's Harbor inputs under the host workspace."""
    workspace_path = workspace.expanduser().resolve()
    run_root = workspace_path / "tmp" / "experimentalist-openshell" / "trusted-envelopes" / f"run-{uuid4().hex}"
    catalog_root = run_root / "catalog"

    if plan.train_dataset == plan.validation_dataset and plan.train_anchor == plan.validation_anchor:
        train_source = validation_source = Path(
            await resolve_dataset(
                plan.train_dataset,
                plan.train_anchor,
                registry_url=plan.registry_url,
            )
        )
    else:
        train_value, validation_value = await asyncio.gather(
            resolve_dataset(
                plan.train_dataset,
                plan.train_anchor,
                registry_url=plan.registry_url,
            ),
            resolve_dataset(
                plan.validation_dataset,
                plan.validation_anchor,
                registry_url=plan.registry_url,
            ),
        )
        train_source = Path(train_value)
        validation_source = Path(validation_value)

    train = register_dataset_envelope(
        train_source,
        catalog_root=catalog_root,
        name="train",
        provenance=plan.train_dataset,
    )
    validation = register_dataset_envelope(
        validation_source,
        catalog_root=catalog_root,
        name="validation",
        provenance=plan.validation_dataset,
    )
    template_path: Path | None = None
    if plan.task_template is not None:
        template_source = Path(plan.task_template).expanduser().resolve()
        template = register_dataset_envelope(
            template_source,
            catalog_root=catalog_root,
            name="task-template",
            provenance=plan.task_template,
        )
        template_path = template.dataset_path

    return PreparedTrustedInputs(
        catalog_root=catalog_root,
        train_dataset=train.dataset_path,
        validation_dataset=validation.dataset_path,
        task_template=template_path,
    )
