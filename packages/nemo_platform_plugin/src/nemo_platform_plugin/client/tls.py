# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""TLS configuration shared by NeMo Platform plugin clients."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import TypedDict

NMP_CLIENT_SSL_CERT_FILE_ENVVAR = "NMP_CLIENT_SSL_CERT_FILE"


class HttpxTLSConfig(TypedDict, total=False):
    """TLS kwargs passed to HTTPX client and request calls."""

    verify: str


def httpx_tls_config_from_env(
    env: Mapping[str, str] | None = None,
    *,
    cert_file_envvars: Sequence[str] = (NMP_CLIENT_SSL_CERT_FILE_ENVVAR,),
) -> HttpxTLSConfig:
    """Return HTTPX TLS kwargs for NeMo Platform client requests."""
    for envvar in cert_file_envvars:
        cert_file = (env[envvar] if env is not None and envvar in env else os.environ.get(envvar, "")).strip()
        if cert_file:
            return {"verify": cert_file}
    return {}
