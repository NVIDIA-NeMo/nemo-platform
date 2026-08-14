---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

description: Review a documentation file for quality and issues
---
Review the documentation file: $ARGUMENTS

Check for these issues:

## Content Quality
- [ ] Clear and accurate technical information
- [ ] Appropriate level of detail for the audience
- [ ] Consistent terminology throughout
- [ ] Complete code examples that work

## Formatting & Style
- [ ] Proper MyST markdown syntax
- [ ] Consistent heading hierarchy (no skipped levels)
- [ ] Code blocks have appropriate language tags
- [ ] Lists are formatted consistently

## Links & References
- [ ] Cross-references use proper MyST syntax: `{ref}`, `{doc}`, `{func}`
- [ ] External links are valid and not broken
- [ ] Internal links point to existing anchors/pages

## Accessibility
- [ ] Images have alt text
- [ ] Tables have headers
- [ ] Important info not conveyed by color alone

Provide a summary of issues found and suggested fixes.

