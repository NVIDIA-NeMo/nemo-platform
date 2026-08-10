# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# The whole task environment, built once and referenced by every task through
# [environment].docker_image. NOOA is baked in rather than installed during
# Harbor setup, so per-trial setup stays near zero and only a cached image build
# pays. The pinned revision must match the workspace root pyproject.toml; a test
# asserts it.

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.9.14 /uv /bin/uv

# `uv pip install --system` rather than `uv sync`: there is no project here, just
# one pinned dependency going into the image's own interpreter.
RUN uv pip install --system --no-cache \
    "nooa[tracing] @ git+https://github.com/NVIDIA-NeMo/labs-OO-Agents.git@6e0274dd03f883254a084cfb9f871ea580e03434"

WORKDIR /app
RUN mkdir -p /app/artifacts /app/traces /app/data
COPY records.json /app/data/records.json
