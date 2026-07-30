# Managed by `nemo agents package` — safe to delete if you take ownership.
ARG BASE_IMAGE_URL=nvcr.io/nvidia/base/ubuntu
ARG BASE_IMAGE_TAG=noble-20260217
ARG PYTHON_VERSION=3.13
ARG NAT_VERSION=1.8.0
FROM ${BASE_IMAGE_URL}:${BASE_IMAGE_TAG}
ARG PYTHON_VERSION
ARG NAT_VERSION

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1

# Keep the uv-managed Python in a world-readable location and use copy
# link-mode so the venv is self-contained (no cross-directory symlinks),
# letting the non-root runtime user exec it without needing /root access.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_LINK_MODE=copy

RUN apt-get update && \
    apt-get install -y --no-install-recommends g++ gcc ca-certificates curl && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /workspace

COPY ./ /workspace

# Project mode.  ``pyproject.toml`` is the single source of truth: it must
# declare ``nvidia-nat[...]`` (for the ``nat`` CLI), a concrete ``version``
# (or a container-resolvable dynamic version), and every runtime dep.
# ``uv sync`` is deliberately not used because it honors
# ``[tool.uv.sources]`` path overrides pointing at sibling workspace
# packages that typically do not exist inside the build context.
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv,sharing=locked \
    uv venv --python ${PYTHON_VERSION} /workspace/.venv && \
    . /workspace/.venv/bin/activate && \
    uv pip install . && \
    chmod -R a+rX /opt/uv /workspace/.venv

LABEL org.opencontainers.image.title="builtin-nemo-agent" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.authors="NVIDIA" \
      org.opencontainers.image.created="2026-07-22T20:51:42.179931+00:00" \
      org.opencontainers.image.description="Built-in NeMo Platform agent — a LangChain Deep Agent that uses the NeMo SDK to perform platform tasks." \
      org.opencontainers.image.revision="" \
      org.opencontainers.image.source="" \
      com.nemo.agent.id="790bd61b98d0" \
      com.nemo.agent.framework="nemo_agent_toolkit" \
      com.nemo.agent.nat-version="1.8.0" \
      com.nemo.agent.contract-version="0.0.0"

ENV NAT_CONFIG_FILE=/workspace/src/nemo_agent/nemo-agent.yml

ENV PATH="/workspace/.venv/bin:$PATH"

# Some modern base images (notably Ubuntu 24.04 "noble" and the NVIDIA base
# images derived from it) ship with a default unprivileged user at
# uid=1000/gid=1000.  Reclaim 1000 for ``agent`` *by id, not by name* so this
# layer is portable across older base images (where 1000 is free; the guarded
# delete is a no-op) and across future base images that might rename the
# default user.
RUN if getent passwd 1000 >/dev/null; then userdel -rf "$(getent passwd 1000 | cut -d: -f1)" 2>/dev/null || true; fi && \
    if getent group  1000 >/dev/null; then groupdel -f "$(getent group  1000 | cut -d: -f1)" 2>/dev/null || true; fi && \
    groupadd -g 1000 agent && useradd -u 1000 -g agent -m agent && \
    chown -R agent:agent /workspace
USER agent

ENTRYPOINT ["sh", "-c", "exec nat serve --config_file=$NAT_CONFIG_FILE --host 0.0.0.0"]
