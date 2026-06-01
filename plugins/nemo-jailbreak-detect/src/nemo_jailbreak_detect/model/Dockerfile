# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Self-hosted replacement for nvcr.io/nim/nvidia/nemoguard-jailbreak-detect.
# Bakes the random forest into the image; the Snowflake embedder is pulled by
# transformers on first load (or pre-download it here too if you want a fully
# offline image).
FROM pytorch/pytorch:2.9.1-cuda12.6-cudnn9-runtime

RUN apt-get update && apt-get install -y --no-install-recommends git wget && apt-get clean && rm -rf /var/lib/apt/lists/*

# Default to GPU; override to "cpu" for CPU-only deployments.
ENV JAILBREAK_CHECK_DEVICE=cuda:0

# Cache the Snowflake embedder under the mounted cache dir so it isn't
# re-downloaded on every container restart. The backend mounts a host path at
# /opt/nim/.cache/, and HF_HOME points transformers there.
ENV HF_HOME=/opt/nim/.cache/huggingface

# Pre-download the random forest so the container is ready without HF access.
WORKDIR /models
RUN wget -q https://huggingface.co/nvidia/NemoGuard-JailbreakDetect/resolve/main/snowflake.onnx
ENV EMBEDDING_CLASSIFIER_PATH=/models

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the model server sources (classifier.py + server.py).
COPY classifier.py server.py ./

EXPOSE 8000
ENTRYPOINT ["python", "server.py", "start"]
CMD ["--port=8000"]
