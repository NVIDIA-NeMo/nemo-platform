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
    """Return whether platform authentication is enabled."""
    try:
        from nmp.common.config import get_auth_config

        return bool(get_auth_config().enabled)
    except Exception:
        logger.debug("Could not resolve auth config; assuming auth disabled", exc_info=True)
        return False
