# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# CPU image for the jailbreak-detection model server. Lean, builds natively on
# both amd64 and arm64 (e.g. Apple Silicon) for local/dev testing. For GPU
# deployments (pods / DGX) use `Dockerfile-GPU`.
#
# Self-hosted replacement for nvcr.io/nim/nvidia/nemoguard-jailbreak-detect.
# The random forest runs on CPU (onnxruntime) and the embedder runs on CPU here;
# neither requires a GPU.
FROM python:3.11-slim

ENV JAILBREAK_CHECK_DEVICE=cpu

# Model weights are downloaded at first start, not baked into the image:
#   - the random forest (snowflake.onnx) into EMBEDDING_CLASSIFIER_PATH
#   - the Snowflake embedder into HF_HOME
# nvidia/NemoGuard-JailbreakDetect is a gated repo, so provide HF auth at RUN
# time: `docker run -e HF_TOKEN=...`. Mount these dirs to persist downloads.
ENV HF_HOME=/opt/nim/.cache/huggingface
ENV EMBEDDING_CLASSIFIER_PATH=/opt/nim/.cache/jailbreak-detect

WORKDIR /app
COPY requirements.txt .
# Install CPU-only torch (avoids pulling the multi-GB CUDA wheel on amd64), then
# the rest. torch is already pinned in requirements.txt and will be satisfied.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Copy only the model server sources (classifier.py + server.py).
COPY classifier.py server.py ./

EXPOSE 8000
ENTRYPOINT ["python", "server.py", "start"]
CMD ["--port=8000"]
