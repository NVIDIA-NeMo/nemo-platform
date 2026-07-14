# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Tests for output fileset metadata helpers."""

from nmp.customization_common.tasks.file_io_metadata import build_output_metadata


class TestBuildOutputMetadata:
    def test_extracts_canonical_fields(self) -> None:
        meta = build_output_metadata(
            model="Qwen/Qwen3-0.6B",
            finetuning_type="all_weights",
            save_method="lora",
            output_type="model",
        )
        assert meta == {
            "model": "Qwen/Qwen3-0.6B",
            "finetuning_type": "all_weights",
            "save_method": "lora",
            "output_type": "model",
        }

    def test_omits_save_method_when_not_provided(self) -> None:
        meta = build_output_metadata(
            model="default/base-model",
            finetuning_type="all_weights",
            output_type="model",
        )
        assert meta == {
            "model": "default/base-model",
            "finetuning_type": "all_weights",
            "output_type": "model",
        }
