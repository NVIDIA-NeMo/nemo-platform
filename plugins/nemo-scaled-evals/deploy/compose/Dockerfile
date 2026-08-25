# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Local compose image for the Phase-1 scaled-evals plugin: the platform API and
# both scaled-evals workers run from this one image.
#
# This is NOT the platform's shipping image. `docker/Dockerfile.nmp-api` builds
# that one through bake, from base images that live in internal registries, and
# it installs the `functional-services` group — which does not include this
# ephemeral plugin. Here we install the workspace scoped to the plugin instead
# (`--package`), which drops ~370 packages (guardrails, transformers, NAT) that
# a scaled-evals-only API never imports.
#
# Build from the repo root:
#   docker build -f plugins/nemo-scaled-evals/deploy/compose/Dockerfile .

ARG PYTHON_VERSION=3.12
# Client and daemon come from the same image so buildctl cannot skew past buildkitd.
ARG BUILDKIT_IMAGE=moby/buildkit:rootless@sha256:946cf909534b789c9b84af75e6d4f8cb23c3b9cb387daec5ba0f4878a3e4647c
ARG KUBECTL_VERSION=v1.33.2

FROM ${BUILDKIT_IMAGE} AS buildkit

# =============================================================================
# Harbor runner — the thing that actually executes an evaluation.
#
# The dispatch worker spawns `$HARBOR_DIR/.venv/bin/harbor run` as a subprocess,
# and Harbor's K8sSandboxEnvironment (from sandbox-k8s) creates the Sandbox CRs.
# Neither is a dependency of the plugin, so both are installed here rather than
# through uv sync. sandbox-k8s is pinned to the version matching the cluster's
# agent-sandbox CRD; harbor comes from the curated catalog the plugin ships.
#
# ponytail: only the catalog's default version is built, where upstream builds
# every selectable version. Ceiling: requesting a non-default framework_version
# fails with a missing runner. Upgrade path: loop over selectable-versions.txt
# as upstream's Dockerfile does — it costs one venv and ~1 min per extra version.
# =============================================================================
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS harbor

# Additional package index for the harbor / sandbox-k8s wheels, for deployments
# that mirror them privately. Empty means PyPI only, so a build has to opt in
# rather than inherit somebody else's index:
#   --build-arg HARBOR_EXTRA_INDEX_URL=https://<index>/simple
ARG HARBOR_EXTRA_INDEX_URL=""

COPY plugins/nemo-scaled-evals/src/scaled_evals/data/harbor_runner_qualifications.json \
     /opt/harbor/qualification-catalog.json

RUN set -eu; \
    python -c 'import json,sys; c=json.load(open(sys.argv[1])); v=c["default_version"]; assert c["releases"][v]["selectable"]; print(v)' \
        /opt/harbor/qualification-catalog.json > /opt/harbor/default-version.txt; \
    python -c 'import json,sys; print(json.load(open(sys.argv[1]))["sandbox_k8s"]["version"])' \
        /opt/harbor/qualification-catalog.json > /opt/harbor/sandbox-k8s-version.txt

RUN --mount=type=cache,target=/root/.cache/uv \
    set -eu; \
    version="$(cat /opt/harbor/default-version.txt)"; \
    sandbox_k8s_version="$(cat /opt/harbor/sandbox-k8s-version.txt)"; \
    runner="/opt/harbor/${version}"; \
    uv venv "${runner}/.venv"; \
    VIRTUAL_ENV="${runner}/.venv" uv pip install \
        "harbor==${version}" "sandbox-k8s[harbor]==${sandbox_k8s_version}" \
        ${HARBOR_EXTRA_INDEX_URL:+--extra-index-url "$HARBOR_EXTRA_INDEX_URL"}; \
    "${runner}/.venv/bin/python" -c \
        'import importlib.metadata as m, sys; assert m.version("harbor") == sys.argv[1]; assert m.version("sandbox-k8s") == sys.argv[2]' \
        "${version}" "${sandbox_k8s_version}"

# Upstream sandbox-k8s lacks emptyDir mounts for /solution, /tests, /logs and
# /installed-agent, which the oracle verifier path needs. Overlay the same
# patched adapter the standalone image uses, in place, located via importlib.
COPY plugins/nemo-scaled-evals/harbor-patches/sandbox_k8s_harbor.py /tmp/sandbox_k8s_harbor.py
COPY plugins/nemo-scaled-evals/harbor-patches/patch_sandbox_k8s_root.py /tmp/patch_sandbox_k8s_root.py
RUN set -eu; \
    runner="/opt/harbor/$(cat /opt/harbor/default-version.txt)"; \
    harbor_py="$("${runner}/.venv/bin/python" -c 'import importlib.util; print(importlib.util.find_spec("sandbox_k8s.harbor").origin)')"; \
    cp /tmp/sandbox_k8s_harbor.py "$harbor_py"; \
    "${runner}/.venv/bin/python" /tmp/patch_sandbox_k8s_root.py "$(dirname "$harbor_py")"

# Harbor resolves jobs_dir relative to its own root, so point it at the path the
# runtime mounts writable. /opt/harbor itself stays read-only.
RUN set -eu; \
    version="$(cat /opt/harbor/default-version.txt)"; \
    ln -s "${version}" /opt/harbor/default; \
    rm -rf "/opt/harbor/${version}/jobs"; \
    ln -s /var/lib/scaled-evals/harbor-jobs "/opt/harbor/${version}/jobs"

FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim

# Both the API (`GET /v1/readyz`) and the build worker shell out to buildctl.
COPY --from=buildkit /usr/bin/buildctl /usr/local/bin/buildctl

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY . /app

# nmp-platform-runner is what serves the plugin (`nemo services run`); it is not
# in the plugin's dependency closure, since the runner loads plugins rather than
# the other way round. It costs 3 extra packages.
#
# nmp-entities is not needed by this plugin at all: the runner's startup banner
# imports `nmp.core.entities.config` unconditionally to print the database it is
# using, but does not declare nmp-entities as a dependency. A full `uv sync`
# hides that, so it only shows up in a scoped install like this one. 28 packages.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
        --package nemo-scaled-evals-plugin \
        --package nmp-platform-runner \
        --package nmp-entities

ENV PATH="/app/.venv/bin:$PATH"

# Dispatch tears down sandboxes, pods and networkpolicies by shelling out to
# kubectl, so it has to be on PATH even though nothing else in the image uses it.
ARG KUBECTL_VERSION
RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends curl ca-certificates \
    && arch="$(dpkg --print-architecture)" \
    && curl -fsSLo /usr/local/bin/kubectl \
        "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${arch}/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Harbor venv (with the patched adapter) plus the task harness tree that
# SANDBOX_K8S_CONFIG_PATH and BROKEN_PYTHON_TASK_PATH point into.
COPY --from=harbor /opt/harbor /opt/harbor
COPY plugins/nemo-scaled-evals/examples/tasks /harness/tasks
# 0777 because the runtime picks the uid; the k8s manifests mount a writable
# volume over this path anyway, so this only matters for bare `docker run`.
RUN mkdir -p /var/lib/scaled-evals/harbor-jobs \
    && chmod 0777 /var/lib/scaled-evals/harbor-jobs
ENV HARBOR_DIR=/opt/harbor/default

EXPOSE 8080

CMD ["nemo", "services", "run", "--services", "scaled-evals", "--host", "0.0.0.0", "--port", "8080"]
