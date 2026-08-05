# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

FROM nvcr.io/nvidia/nemo-platform/nmp-api:0.3.0@sha256:852758b994aaca5a9646a163fffaf46a20938b7e0aa10928c275e0d4a32d0723

USER 0

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --yes --no-install-recommends jq procps ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY config/nmp-eval-config.yaml /etc/nmp/eval.yaml
COPY scripts/nmp-eval-bootstrap /usr/local/bin/nmp-eval-bootstrap

RUN chmod 0555 /usr/local/bin/nmp-eval-bootstrap \
    && chmod 0444 /etc/nmp/eval.yaml

ENV PATH="/app/.venv/bin:${PATH}"

WORKDIR /workspace

# Astra supplies the sandbox keepalive command. Do not inherit the NMP image's
# `nemo services run` entrypoint or its default arguments.
ENTRYPOINT []
CMD []
