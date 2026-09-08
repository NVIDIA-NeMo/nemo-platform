# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Errors the broker returns to the untrusted job sandbox."""

from sandboxed_gym.wire import BrokerErrorCode


class BrokerRequestError(Exception):
    """A request the broker refuses, carrying its wire error code and HTTP status.

    The message is returned to the caller verbatim, so raise this only with text that is safe to
    disclose: the caller's own input (a rejected field name or image reference) or a policy
    statement. Backend internals are logged instead.
    """

    def __init__(self, code: BrokerErrorCode, message: str, *, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
