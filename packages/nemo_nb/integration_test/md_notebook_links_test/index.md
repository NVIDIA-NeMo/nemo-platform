---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

title: "Integration Test Documentation"
description: "Test documentation for nemo-nb markdown notebook processing"
---

<!-- @nemo-nb: process -->

(integration-test-index)=
# Integration Test Documentation

This is a test documentation set to verify that markdown notebook files are properly converted and linked through the Sphinx build process.

## Overview

This test suite demonstrates:
- Markdown notebook format with frontmatter
- Cross-page linking within the documentation
- Code cells with outputs
- MyST markdown syntax support

## Quick Start

Follow our [Getting Started Guide](./getting-started.md) to learn the basics.

## Configuration

For detailed configuration options, see the [Configuration Reference](./configuration.md).

## Example Code Cell
<!-- @nemo-nb: cell python -->
# Simple Python example
def greet(name: str) -> str:
	"""Return a greeting message."""
	return f"Hello, {name}!"

# Test the function
message = greet("World")
print(message)
<!-- @nemo-nb: output stream stdout -->
Hello, World!

## Next Steps

- Read the [Getting Started Guide](./getting-started.md)
- Review [Configuration Options](./configuration.md)
- Explore advanced features