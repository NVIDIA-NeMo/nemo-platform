---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

title: "Bidirectional Conversion Test"
description: "Sample notebook for testing MD ? IPYNB conversion fidelity"
tags: ["test", "conversion", "fidelity"]
---

# Bidirectional Conversion Test

This notebook tests all output types for MD ? IPYNB conversion.

## Output Type: stream (stdout)

```python

print("This is stdout output")
```

## Output Type: stream (stderr)

```python

import sys

print("This is stderr output", file=sys.stderr)
```

## Output Type: execute_result

```python

# Expression result
21 * 2
```

## Output Type: display_data

```python

from IPython.display import display

data = {"key": "value", "number": 123}
display(data)
```

## Output Type: error

```python

# This will raise an error
raise ValueError("This is a test error")
```

## Multiple Outputs

```python

print("First output")
print("Second output")
50 + 50
```

## Special Characters

Testing special characters: `$`, `#`, `@`

```python

print("Special: $ # @")
```