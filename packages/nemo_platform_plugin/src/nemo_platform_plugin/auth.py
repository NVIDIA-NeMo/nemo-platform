# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Auth helpers exposed to plugins.

Plugins must not import ``nmp_common`` directly. This module wraps the pieces of
the platform auth configuration that plugins need. The underlying auth config
lives in ``nmp_common`` (only present in the platform process image), so it is
imported lazily and failures degrade to "disabled" rather than raising in
environments without it.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def platform_auth_enabled() -> bool:
    """Return whether platform authentication is enabled.

    Returns ``False`` on any failure to resolve the auth config. The realistic
    failure is ``ImportError``: ``nmp_common`` ships only in the platform process
    image, so when this package is used standalone (outside the platform) there
    is no auth config and "disabled" is the correct answer.

    Other failures are effectively unreachable in the context that matters here
    (the deployment controller, which runs *inside* the platform image): a
    missing config file resolves to defaults (``enabled=False``) rather than
    raising, and a malformed/invalid config file would have already crashed the
    platform service at startup before any deployment is reconciled. The config
    read is cached from that successful startup load. We therefore accept the
    narrow, largely theoretical fail-open window rather than propagate and block
    deployments on a transient/unexpected error.
    """
    try:
        from nmp.common.config import get_auth_config

        return bool(get_auth_config().enabled)
    except Exception:
        logger.debug("Could not resolve auth config; assuming auth disabled", exc_info=True)
        return False
