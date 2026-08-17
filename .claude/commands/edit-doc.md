---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

description: Edit a documentation file with best practices
---
Help edit the documentation file: $ARGUMENTS

Follow these guidelines when editing:

1. **Preserve voice and style** - Match the existing documentation tone
2. **Use MyST markdown** - This project uses MyST Parser for extended markdown
3. **Check cross-references** - Ensure any `{ref}`, `{doc}`, or `{func}` links are valid
4. **Validate code blocks** - Ensure code examples are syntactically correct
5. **Keep it concise** - Documentation should be clear and scannable
6. **Review custom extensions** - Review `docs/_extensions` as necessary for custom formats

After making edits:
- Suggest running `/build-docs` to verify the changes compile
- Point out any potential broken references or issues

