# Copyright (c) 2026, NVIDIA CORPORATION.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Errors the broker returns to the untrusted job sandbox."""

from nemo_gym.sandbox.broker import BrokerErrorCode


class BrokerRequestError(Exception):
    """A request the broker refuses, carrying its wire error code and HTTP status.

    The message is returned to the caller verbatim, so raise this only with text that is safe to
    disclose: the caller's own input (a rejected field name or image reference) or a policy
    statement. Backend internals are logged instead.
    """

    def __init__(
        self, code: BrokerErrorCode, message: str, *, status_code: int
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
