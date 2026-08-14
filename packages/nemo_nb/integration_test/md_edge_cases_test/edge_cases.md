---
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
title: "Edge Cases Test for Markdown Parsing"
description: "Testing various messed up markdown scenarios"
tags: ["test", "edge-cases", "robustness"]
---
<!-- @nemo-nb: process -->

# Edge Cases Test

Testing the robustness of markdown to notebook conversion with various "messed up" markdown.

## Test 1: Empty Code Block

```python
```

<!-- @nemo-nb: output -->
(no output)

## Test 2: Excessive Blank Lines





```python
print("After many blank lines")
```

<!-- @nemo-nb: output -->
After many blank lines

## Test 3: Regular HTML Comments Near Code

<!-- This is just a regular comment, not a marker -->
Some text explaining the code below.
<!-- Another regular comment -->

```python
print("Code near regular HTML comments")
```

<!-- @nemo-nb: output -->
Code near regular HTML comments

## Test 4: Unicode and Emoji in Content

```python
print("Hello ?? World ??")
print("Special chars: ? ? ? ?")
```

<!-- @nemo-nb: output -->
Hello ?? World ??
Special chars: ? ? ? ?

## Test 5: Broken Markdown Near Markers

[broken link]()
###NoSpaceAfterHashes
**unclosed bold

```python
print("Code near broken markdown")
```

<!-- @nemo-nb: output -->
Code near broken markdown

## Test 6: Code Containing Triple Backticks

Using 4 backticks to fence code containing 3 backticks:

````python
markdown_text = """
```python
nested = True
```
"""
print(markdown_text)
````

<!-- @nemo-nb: output -->
```python
nested = True
```

## Test 7: Output with Code-Like Content

```python
print("Example usage:")
```

<!-- @nemo-nb: output -->
Example usage:

To run this, use:
```
some_function()
```

## Test 8: Special Characters Not in Markers

```python
# Characters like $ # @ are fine here
price = "$100"
hashtag = "#python"
email = "user@example.com"
print(f"{price} {hashtag} {email}")
```

<!-- @nemo-nb: output -->
$100 #python user@example.com

## Test 9: Zero Blank Lines Before Output
```python
print("No blank line before output marker")
```
<!-- @nemo-nb: output -->
No blank line before output marker

## Test 10: Trailing Whitespace on Lines

```python
print("Line with trailing spaces")    
x = 1   
y = 2	
```

<!-- @nemo-nb: output -->
Line with trailing spaces

## Test 11: Very Long Line in Code

```python
very_long_variable_name = "This is a very long string that goes on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and might be over 200 characters long"
print(very_long_variable_name)
```

<!-- @nemo-nb: output -->
This is a very long string that goes on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and on and might be over 200 characters long

## Test 12: Code with HTML-Like Comments

```python
# This comment has HTML-like content: <!-- but it's not a marker -->
# Another one: <!-- @not-a-marker: just text -->
x = "<!-- also not a marker -->"
print(x)
```

<!-- @nemo-nb: output -->
<!-- also not a marker -->

## Test 13: Multiple Outputs for One Cell

```python
print("First output")
print("Second output")
42 + 8
```

<!-- @nemo-nb: output -->
First output
Second output
<!-- @nemo-nb: output execute_result -->
50

## Test 14: List Items Near Code Blocks

Here's a list:
- Item 1
- Item 2
  - Nested item

```python
print("Code after a list")
```

<!-- @nemo-nb: output -->
Code after a list

## Test 15: Blockquote Near Code

> This is a blockquote.
> It has multiple lines.

```python
print("Code after blockquote")
```

<!-- @nemo-nb: output -->
Code after blockquote

## Test 16: HTML Entities in Markdown

Testing HTML entities: &lt; &gt; &amp; &nbsp; &copy;

```python
print("Code near HTML entities")
```

<!-- @nemo-nb: output -->
Code near HTML entities

## Test 17: Empty Output Block

```python
# Code with no visible output
x = 1 + 1
```

<!-- @nemo-nb: output -->


## Test 18: Inline Code Near Fenced Code

Use `print()` function like this:

```python
print("Hello")
```

<!-- @nemo-nb: output -->
Hello

## Test 19: Mixed Tab and Space Indentation

```python
def function():
	# This line has a tab
    # This line has spaces
	return True
```

<!-- @nemo-nb: output execute_result -->
True

## Test 20: Markdown Header Between Code and Output

This should probably fail or behave unexpectedly:

```python
print("Before header")
```

### Unexpected Header Here

<!-- @nemo-nb: output -->
Before header
