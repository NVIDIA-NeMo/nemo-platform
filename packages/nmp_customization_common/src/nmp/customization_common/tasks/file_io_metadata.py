# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Helpers for stamping output fileset metadata during customization uploads."""


def build_output_metadata(
    *,
    model: str,
    finetuning_type: str,
    output_type: str,
    save_method: str | None = None,
) -> dict:
    """Build the metadata dict stamped onto the output fileset.

    Captures the bits a downstream consumer (model-entity creation,
    deployment) needs about this artefact without re-deriving them
    from the training spec.
    """
    metadata: dict[str, str] = {
        "model": model,
        "finetuning_type": finetuning_type,
        "output_type": output_type,
    }
    if save_method is not None:
        metadata["save_method"] = save_method
    return metadata
