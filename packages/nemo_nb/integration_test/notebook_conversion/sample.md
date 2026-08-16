---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

title: "Bidirectional Conversion Test"
description: "Sample notebook for testing MD ? IPYNB conversion fidelity"
tags: ["test", "conversion", "fidelity"]
---
<!-- @nemo-nb: process -->
<!-- @nemo-nb: notebook-convert-4-space-to-tab -->

# Bidirectional Conversion Test

This notebook tests all output types for MD ? IPYNB conversion.

## Output Type: stream (stdout)

```python
print("This is stdout output")
```

<!-- @nemo-nb: output -->
This is stdout output

## Output Type: stream (stderr)

```python
import sys

print("This is stderr output", file=sys.stderr)
```

<!-- @nemo-nb: output stream stderr -->
This is stderr output

## Output Type: execute_result

```python
# Expression result
21 * 2
```

<!-- @nemo-nb: output execute_result -->
42

## Output Type: display_data

```python
from IPython.display import display

data = {"key": "value", "number": 123}
display(data)
```

<!-- @nemo-nb: output display_data -->
{'key': 'value', 'number': 123}

## Output Type: error

```python
# This will raise an error
raise ValueError("This is a test error")
```

<!-- @nemo-nb: output error -->
[0;31m---------------------------------------------------------------------------[0m
[0;31mValueError[0m                                Traceback (most recent call last)
Cell [0;32mIn[5], line 2[0m
[1;32m      1[0m [38;5;66;03m# This will raise an error[39;00m
[0;32m----> 2[0m [38;5;28;01mraise[39;00m [38;5;167;01mValueError[39;00m([38;5;124m"[39m[38;5;124mThis is a test error[39m[38;5;124m"[39m)

[0;31mValueError[0m: This is a test error

## Multiple Outputs

```python
print("First output")
print("Second output")
50 + 50
```

<!-- @nemo-nb: output -->
First output
Second output
<!-- @nemo-nb: output execute_result -->
100

## Special Characters

Testing special characters: `$`, `#`, `@`

```python
print("Special: $ # @")
```

<!-- @nemo-nb: output -->
Special: $ # @
