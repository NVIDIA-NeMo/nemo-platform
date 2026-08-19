# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Internal OpenShell entrypoint; never used by the host CLI directly."""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from nemo_experimentalist_plugin.client import make_client
from nemo_experimentalist_plugin.entities import DatasetRef
from nemo_experimentalist_plugin.openshell.preparation import SandboxRunManifest

_RUNTIME_MARKER_ENV = "NEMO_EXPERIMENTALIST_OPEN_SHELL_RUNTIME"
_BRIDGE_URL_ENV = "NEMO_EXPERIMENTALIST_HARBOR_BRIDGE_URL"


def _contained_path(root: Path, relative: str) -> Path:
    value = (root / relative).resolve()
    try:
        value.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Prepared sandbox path escapes its input root: {relative!r}") from exc
    return value


async def run_prepared_manifest(manifest_path: Path, *, output_dir: Path) -> str:
    """Execute only a host-prepared, credential-free manifest."""
    if os.environ.get(_RUNTIME_MARKER_ENV) != "1":
        raise RuntimeError("The Experimentalist inner runner requires an OpenShell runtime")
    if not os.environ.get(_BRIDGE_URL_ENV):
        raise RuntimeError(f"{_BRIDGE_URL_ENV} is required in the OpenShell runtime")
    manifest_file = manifest_path.expanduser().resolve()
    manifest = SandboxRunManifest.model_validate_json(manifest_file.read_text(encoding="utf-8"))
    root = manifest_file.parent
    agent = _contained_path(root, manifest.agent)
    train = _contained_path(root, manifest.train_dataset)
    validation = _contained_path(root, manifest.validation_dataset)
    template = _contained_path(root, manifest.task_template) if manifest.task_template is not None else None
    insight = _contained_path(root, manifest.insight) if manifest.insight is not None else None
    agent_spec = _contained_path(root, manifest.agent_spec) if manifest.agent_spec is not None else None
    skills = [_contained_path(root, value) for value in manifest.framework_skills_dirs]
    config = manifest.config.model_copy(
        update={
            "outcome_evaluator": "remote-harbor",
            "outcome_evaluator_config": {
                **manifest.config.outcome_evaluator_config,
                "bridge_url": os.environ[_BRIDGE_URL_ENV],
            },
        }
    )

    from nemo_experimentalist_plugin.experimentalist.run import run_experimentalist  # noqa: PLC0415

    client = make_client(os.environ.get("NMP_BASE_URL", "http://host.openshell.internal:8080"))
    try:
        return await run_experimentalist(
            agent=str(agent),
            agent_spec=str(agent_spec) if agent_spec is not None else None,
            insight=insight,
            train_dataset=DatasetRef(uri=train.as_uri(), metadata={"id": "train"}),
            validation_dataset=DatasetRef(uri=validation.as_uri(), metadata={"id": "validation"}),
            task_template=(
                DatasetRef(uri=template.as_uri(), metadata={"id": "task-template"}) if template is not None else None
            ),
            experiment_dir=output_dir,
            workspace=manifest.workspace,
            client=client,
            config=config,
            framework_skills_dirs=skills,
        )
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(asyncio.run(run_prepared_manifest(args.manifest, output_dir=args.output)))


if __name__ == "__main__":
    main()
