---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
title: "Getting Started Guide"
description: "Quick start guide for the integration test"
---

<!-- @nemo-nb: process -->

(getting-started)=
# Getting Started Guide

Welcome to the integration test! This guide will walk you through the basics.

## Prerequisites

Before you begin, make sure you have:
- Python 3.11 or later
- Required dependencies installed

## Basic Example

Here's a simple example to get you started:
<!-- @nemo-nb: cell python -->
# Import required libraries
import json
from pathlib import Path

# Create a simple data structure
data = {
	"name": "Integration Test",
	"version": "1.0.0",
	"features": ["markdown", "notebooks", "sphinx"]
}

# Display the data
print(json.dumps(data, indent=2))
<!-- @nemo-nb: output stream stdout -->
{
  "name": "Integration Test",
  "version": "1.0.0",
  "features": [
	"markdown",
	"notebooks",
	"sphinx"
  ]
}
<!-- @nemo-nb: cell markdown -->
## Working with Lists
<!-- @nemo-nb: cell python -->
# Process a list of items
items = ["apples", "bananas", "cherries"]

for i, item in enumerate(items, 1):
	print(f"{i}. {item.capitalize()}")
<!-- @nemo-nb: output stream stdout -->
1. Apples
2. Bananas
3. Cherries

## Next Steps

Now that you've completed the basics, check out the [Configuration Reference](./configuration.md) to learn about advanced options.

You can also return to the [main page](./index.md) to see other resources.
