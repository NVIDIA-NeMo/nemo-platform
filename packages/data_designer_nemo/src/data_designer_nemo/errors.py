# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0


class NDDError(Exception):
    """Shared base for all data_designer_nemo errors."""


class NDDInternalError(NDDError): ...


class NDDInvalidConfigError(NDDError): ...


def raise_if_errors(errors: list[NDDError]) -> None:
    """Raise an aggregated ``NDDError`` if ``errors`` is non-empty.

    This is the canonical projection from a ``list[NDDError]`` back to a single
    exception. Any config-level error wins (HTTP 422-class) and surfaces as
    :class:`NDDInvalidConfigError` carrying every error's message; only when
    *every* error is internal do we raise :class:`NDDInternalError` (HTTP
    500-class).

    The "any 422 wins" rule reflects HTTP semantics: an authoritative answer
    about the user's input shouldn't be masked by an unrelated internal
    failure. Every error message — config and internal — is included in the
    aggregated message either way; the exception class reflects whose fault
    it primarily is.
    """
    if not errors:
        return
    aggregated_message = "\n".join(str(e) for e in errors)
    if any(isinstance(e, NDDInvalidConfigError) for e in errors):
        raise NDDInvalidConfigError(aggregated_message)
    raise NDDInternalError(aggregated_message)
