# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

ARG NMP_PYTHON_BASE=nmp-python-base

FROM ${NMP_PYTHON_BASE} AS builder
COPY --from=nmp-workspace . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --only-group experimentalist --no-editable

FROM ${NMP_PYTHON_BASE} AS runtime

LABEL com.nvidia.nemo.experimentalist.openshell-runtime="1"

RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    nftables \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system sandbox \
    && useradd --system --gid sandbox --create-home --home-dir /home/sandbox --shell /bin/bash sandbox \
    && mkdir -p /sandbox \
    && chown sandbox:sandbox /sandbox \
    && touch /etc/nemo-experimentalist-container

COPY --from=builder /app/.venv /app/.venv

ENV HOME=/home/sandbox \
    PATH="/app/.venv/bin:$PATH" \
    XDG_CACHE_HOME=/sandbox/.cache

WORKDIR /sandbox
USER sandbox
