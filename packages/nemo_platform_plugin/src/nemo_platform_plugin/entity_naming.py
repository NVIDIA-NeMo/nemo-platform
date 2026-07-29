# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""The single definition of the entity name rule.

This lives in ``nemo_platform_plugin`` rather than ``nmp_common`` because the
dependency runs that way — ``nmp_common`` depends on this package, so anything
here is importable from both sides. ``nmp.common.entities.constants`` re-exports
these names.

Imports nothing, so modules that need to stay leaf nodes can still use it.

Any Pydantic model declaring ``pattern=NAME_PATTERN`` must also set
``model_config = ConfigDict(regex_engine="python-re")``; the pattern uses
lookaround, which Pydantic's default Rust engine rejects.
"""

# RFC 1035 compliant pattern with temporary support for special characters.
# Allows lowercase letters, digits, hyphens, and temporarily: @, ., +, _
# - Must start with a lowercase letter [a-z]
# - Length: 2-63 characters
# - No consecutive hyphens (--)
# - Must not end with a hyphen
# TODO(#3530): Remove @, ., +, _ once versioning is implemented and predefined target names (e.g., llama-3.2-3b-instruct@v1.0.0+A100) are updated.
NAME_PATTERN = r"^[a-z](?!.*--)[a-z0-9\-@.+_]{1,62}(?<!-)$"

NAME_MAX_LENGTH = 63

NAME_PATTERN_DESCRIPTION = (
    "Name must start with a lowercase letter, be 2-63 characters, "
    "and contain only lowercase letters, digits, and hyphens "
    "(no consecutive hyphens, cannot end with a hyphen)."
)
