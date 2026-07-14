# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Multi-stage image for FabricContainerRuntime. The builder compiles nemo-fabric (maturin/Rust) into
# an isolated venv AND builds Fabric's own `fabric` CLI (the runtime execs `fabric run` to kick off
# the harness). The final stage copies only the venv + the CLI binary + the built-in adapters — no
# source tree and no Rust toolchain. Harness extras are selected via the EXTRAS build arg.
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ARG EXTRAS=hermes,relay
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs -o /tmp/rustup-init.sh \
    && sh /tmp/rustup-init.sh -y --profile minimal \
    && rm -f /tmp/rustup-init.sh
ENV PATH=/root/.cargo/bin:$PATH
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
# Only the maturin build inputs are in the context (see image._stage_source): the native nemo-fabric
# extension is compiled here and the harness/relay wheels are pulled from PyPI — into the venv only.
COPY nemo-fabric /src
RUN pip install --no-cache-dir "/src[${EXTRAS}]"
# Fabric's own CLI (Rust). The runtime execs `fabric run <agent.yaml> --profile … --input-file …`,
# which prints a normalized RunResult to stdout — so no in-image Python driver is needed.
RUN cargo build --release --manifest-path /src/Cargo.toml -p fabric-cli

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /src/target/release/fabric /usr/local/bin/fabric
# The CLI binary resolves built-in adapters from its compile-time repository path
# (CARGO_MANIFEST_DIR/../../python/src/nemo_fabric/adapters); ship just that dir to the baked path so a
# wheel-only image can resolve them. Depends on NeMo-Fabric's installed-adapter-discovery layout
# (see image.py); swap to installing the top-level adapters/* packages once that lands on main.
COPY --from=builder /src/python/src/nemo_fabric/adapters /src/python/src/nemo_fabric/adapters
# The CLI's baked path is the literal `<fabric-core crate>/../../python/src/nemo_fabric/adapters`; the
# kernel needs `/src/crates/fabric-core` to exist to walk the `..`, even though nothing lives there.
RUN mkdir -p /src/crates/fabric-core
ENV PATH=/opt/venv/bin:$PATH
RUN python -c "from nemo_fabric import FabricClient" && fabric version
# Run agent-generated code as a non-root user: this sandbox execs `fabric run` over untrusted,
# agent-produced content, so dropping root narrows the blast radius of a container escape. Pre-create
# and own the fixed /in (seeded inputs) and /out (workspace + results) trees, since a non-root process
# cannot mkdir under / at exec time and the runtime creates /out/{workspace,relay,artifacts,logs} then.
RUN useradd --create-home --uid 1000 sandbox \
 && mkdir -p /in /out \
 && chown -R sandbox:sandbox /in /out
WORKDIR /out
USER sandbox
