# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Self-hosted replacement for nvcr.io/nim/nvidia/nemoguard-jailbreak-detect.
# uv-managed. Weights download at first start (not baked).
#
# Runs on CPU by default. For GPU pods/DGX, run with `--gpus all` and
# `-e JAILBREAK_CHECK_DEVICE=cuda:0` — the Linux torch wheel bundles CUDA, so the
# same image works on both. (For a lean CPU-only image, add uv cpu/cuda extras.)
#
# Build context is this directory (so pyproject.toml + uv.lock + model/ are present):
#   docker build -t nemo/jailbreak-detect:0.1.0 .
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

ENV JAILBREAK_CHECK_DEVICE=cpu \
    HF_HOME=/opt/jailbreak-detect/.cache/huggingface \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY model/classifier.py model/server.py ./

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
ENTRYPOINT ["python", "server.py", "start"]
CMD ["--port=8000"]
