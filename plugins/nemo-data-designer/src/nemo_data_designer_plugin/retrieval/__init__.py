# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Nemotron retrieval SDG helpers for dedicated Data Designer jobs.

Compatibility (slice 0): ``data-designer-retrieval-sdg==0.2.1`` imports against
platform ``data-designer==0.9.1``. ``GenerationRunConfig.model_providers``
accepts ``list[dd.ModelProvider]``. Inject IGW providers resolved by
``RemoteDataDesignerContext.get_model_providers`` and set pipeline
``*_provider`` fields to those provider names. Skip
``build_model_providers`` custom NVIDIA endpoint injection; ``run_generation``
already merges supplied providers with Data Designer defaults.
"""
