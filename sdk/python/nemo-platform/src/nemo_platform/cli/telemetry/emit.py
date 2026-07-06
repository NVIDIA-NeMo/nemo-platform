# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Fire-and-flush emission with three opt-out layers and the first-run notice."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path

from nemo_platform.cli.telemetry.events import PlatformTelemetryEvent
from nemo_platform.cli.telemetry.handler import TelemetryHandler, _telemetry_enabled

logger = logging.getLogger(__name__)

_invocation_opt_out = False

# One random session id per process. It groups every event emitted during a single
# invocation without carrying any user or device identity, and is discarded when the
# process exits. This is the same pattern the Agno framework uses for session_id/run_id.
_SESSION_ID = uuid.uuid4().hex

_NOTICE_TEXT = (
    "NeMo Platform collects anonymous usage data to improve the product. "
    "No prompts, data, or personal information leave your machine. "
    "Turn it off any time with NEMO_TELEMETRY_ENABLED=false.\n"
)


def set_invocation_opt_out(value: bool) -> None:
    """Per-invocation opt-out (e.g. a --no-telemetry flag on the current command)."""
    global _invocation_opt_out
    _invocation_opt_out = value


def _config_opted_out() -> bool:
    """True when the persisted config file sets ``telemetry_enabled: false``."""
    try:
        from nemo_platform.config.config import Config

        cfg = Config.load()
        return getattr(cfg.get_config_file(), "telemetry_enabled", True) is False
    except Exception:
        # A privacy control must fail closed: if we cannot read the config to confirm
        # the user is opted in, treat them as opted out and do not send.
        logger.debug("Could not read telemetry opt-out config; failing closed (opted out)", exc_info=True)
        return True


def telemetry_opted_in() -> bool:
    """Opted in only when all three layers agree: per-invocation, env, and config."""
    if _invocation_opt_out:
        return False
    if not _telemetry_enabled():
        return False
    return not _config_opted_out()


def _client_version() -> str:
    try:
        import nemo_platform

        return nemo_platform.__version__
    except Exception:
        logger.debug("Could not resolve client version for telemetry", exc_info=True)
        return "undefined"


def emit_event(event: PlatformTelemetryEvent) -> None:
    """Best effort. Telemetry must never break a user command."""
    try:
        if not telemetry_opted_in():
            return
        handler = TelemetryHandler(source_client_version=_client_version(), session_id=_SESSION_ID)
        handler.enqueue(event)
        handler.stop()
    except Exception:
        logger.debug("Failed to emit telemetry event", exc_info=True)


def _notice_marker_path() -> Path:
    from nemo_platform.config.config import Config

    return Config.get_default_config_path().parent / "telemetry-notice-shown"


def maybe_print_first_run_notice() -> None:
    """Print the first-run notice to stderr once. Stdout stays machine-clean."""
    try:
        if not telemetry_opted_in():
            return
        marker = _notice_marker_path()
        if marker.exists():
            return
        sys.stderr.write(_NOTICE_TEXT)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
    except Exception:
        logger.debug("Failed to print telemetry notice", exc_info=True)
