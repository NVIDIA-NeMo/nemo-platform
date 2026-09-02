# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

# Sandboxed Gym host, for local execution against the Docker host provider.
#
# This is the development counterpart of the runtime image a cluster would run. It exists so the
# sandboxed path can be *executed* without OpenSandbox or Kubernetes: same runtime module, same
# bootstrap environment, same HTTP contract. It is NOT an isolation boundary -- a Docker container
# is not kata-qemu and enforces no egress policy -- so it validates the code path, not the security
# posture the sandboxed-GRPO RFC requires of a shared cluster.
#
# NeMo-Gym floors at CPython 3.13.14, which is why it cannot be a workspace dependency; an image has
# its own interpreter, so here it installs normally.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NMP_RUNTIME_HTTP_PORT=8080

RUN apt-get update \
    && apt-get install -y --no-install-recommends git curl \
    && rm -rf /var/lib/apt/lists/*

# NeMo-Gym spawns each agent/model/resources server as its own process through `uv`, so the image
# needs it on PATH: without it every server dies at spin-up with "Process ... finished unexpectedly".
RUN pip install --no-cache-dir uv

# NeMo-Gym first: it is the slow layer and changes far less often than the package below it.
RUN pip install --no-cache-dir "nemo-gym==0.5.0"

# The host runtime. Copied as source rather than installed from an index so the image tracks the
# working tree -- the whole point is executing the code we are writing.
COPY packages/sandboxed_gym/pyproject.toml /opt/sandboxed_gym/pyproject.toml
COPY packages/sandboxed_gym/README.md /opt/sandboxed_gym/README.md
COPY packages/sandboxed_gym/src /opt/sandboxed_gym/src
RUN pip install --no-cache-dir "/opt/sandboxed_gym[runtime]"

# Build the per-server venvs now rather than on first run. Gym creates one venv per agent, model and
# resources server the config selects, which is ~3 GB and several minutes -- paid once here instead
# of on every container start.
RUN gym env prefetch "+config_paths=[responses_api_agents/simple_agent/configs/simple_agent.yaml,responses_api_models/inference_provider/configs/inference_provider.yaml,resources_servers/mcqa/configs/mcqa.yaml]" \
      "++policy_base_url=http://127.0.0.1:9/v1" "++policy_api_key=unused" "++policy_model_name=unused" \
      "++simple_agent.responses_api_agents.simple_agent.resources_server.name=mcqa" \
      "++uv_venv_dir=/opt/gym_venvs" "++uv_cache_dir=/opt/uv-cache" \
    || echo "prefetch failed; venvs will be built at run time"

# The offline model endpoint, for local runs with no provider. Not used unless a caller points
# `policy_base_url` at it.
COPY docker/gym-host/model_stub.py /opt/model_stub.py

# Where the provider mounts the environment and the writable workspace.
RUN mkdir -p /job/environment /job/work
WORKDIR /job/work

EXPOSE 8080
CMD ["python", "-m", "sandboxed_gym.runtime.gym_host_runtime"]
