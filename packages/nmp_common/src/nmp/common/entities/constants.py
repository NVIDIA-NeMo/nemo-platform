# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Constants for entity validation."""

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

# Field length constraints
MAX_LENGTH_255 = 255

# Regex patterns for field validation
REGEX_WORD_CHARACTER_DOT_DASH = r"^[\w\-.]+$"
REGEX_WORD_CHARACTER_DOT_DASH_DESCRIPTION = (
    "Allowed characters: letters (a-z, A-Z), digits (0-9), underscores, hyphens, and dots."
)
REGEX_WORD_CHARACTER_DOT_DASH_SLASH = r"^[\w\-./]+$"
REGEX_WORD_CHARACTER_DOT_DASH_OR_BLANK = r"^[\w\-.@:]*$"
REGEX_WORD_CHARACTER_DOT_DASH_OR_BLANK_OR_PLUS = r"^[\w\-\+.@:]*$"

# Special value to indicate all workspaces
ALL_WORKSPACES = "-"

# Default workspace when none is specified
DEFAULT_WORKSPACE = "default"

# System workspace used for platform-provided entities
SYSTEM_WORKSPACE = "system"
