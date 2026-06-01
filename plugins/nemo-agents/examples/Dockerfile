ARG BASE_IMAGE_URL=nvcr.io/nvidia/base/ubuntu
ARG BASE_IMAGE_TAG=22.04_20240212
ARG PYTHON_VERSION=3.13
ARG NAT_VERSION=1.6.0
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

RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv,sharing=locked \
    uv venv --python ${PYTHON_VERSION} /workspace/.venv && \
    . /workspace/.venv/bin/activate && \
    test -n "${NAT_VERSION}" || { echo "NAT_VERSION build-arg is required" >&2; exit 1; } && \
    uv pip install --prerelease=allow "nvidia-nat[most]==${NAT_VERSION}" && \
    chmod -R a+rX /opt/uv /workspace/.venv

LABEL org.opencontainers.image.title="hello_world" \
      org.opencontainers.image.version="26.04.17" \
      org.opencontainers.image.authors="Arpit Singh (SW-CLOUD)" \
      org.opencontainers.image.created="2026-04-17T23:50:42.868232+00:00" \
      org.opencontainers.image.description="react_agent agent" \
      org.opencontainers.image.revision="8d0654a8b8e1edccce579223272e31dcee1608cd" \
      org.opencontainers.image.source="ssh://git@gitlab-master.nvidia.com:12051/aire/microservices/nmp.git" \
      com.nemo.agent.id="e24e65eb1983" \
      com.nemo.agent.framework="nemo_agent_toolkit" \
      com.nemo.agent.nat-version="1.6.0" \
      com.nemo.agent.contract-version="0.1.0"

ENV NAT_CONFIG_FILE=/workspace/hello_world.yaml

ENV PATH="/workspace/.venv/bin:$PATH"

RUN groupadd -g 1000 agent && useradd -u 1000 -g agent -m agent && \
    chown -R agent:agent /workspace
USER agent

ENTRYPOINT ["sh", "-c", "exec nat serve --config_file=$NAT_CONFIG_FILE --host 0.0.0.0"]
