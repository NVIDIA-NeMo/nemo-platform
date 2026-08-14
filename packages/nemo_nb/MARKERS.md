<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# nemo-nb full reference (markers, file types, advanced usage)

_Back to [README.md](README.md)._

This document is intentionally **detailed**. It is meant for power users and tools (including LLMs) that need the full behavior of nemo-nb.

If you just want to use nemo-nb:

- Start with **[README.md](README.md)** for a high-level overview.
- Use **[AUTHORING_GUIDE.md](AUTHORING_GUIDE.md)** for a short guide to markdown notebooks.
- Use **[CLI.md](CLI.md)** for quick CLI examples.

The rest of this file keeps the **comprehensive** reference, including:

- all marker commands and their arguments,
- which markers are **essential** vs **syntax sugar**, and
- how markdown notebooks, `.ipynb` files, and `.sphinx.md` outputs relate.

---

## 1. Core concepts

### 1.1 File types

nemo-nb works with three related file shapes:

1. **Markdown notebook (`.md`, notebook format)**
   - Human-authored source that behaves like a notebook.
   - Uses normal Markdown plus nemo-nb markers.
   - Can be converted to and from `.ipynb`.

2. **Notebook (`.ipynb`)**
   - Standard Jupyter JSON notebook.
   - Executable in Jupyter, VS Code, etc.

3. **Sphinx docs markdown (`.sphinx.md`)**
   - Generated MyST markdown that Sphinx reads.
   - Contains tab-sets, dropdowns, directives, and clean indentation.

**Conversion path:**

```text
Markdown notebook (.md) -> .ipynb -> .sphinx.md -> HTML (via Sphinx)
```

### 1.2 Opt-in processing via `process` marker (essential)

nemo-nb only runs on files that contain the `process` marker.

In markdown cells:

```markdown
<!-- @nemo-nb: process -->
```

In code cells:

```python
# @nemo-nb: process
```

**Rules:**

- At least one `process` marker must appear in the file.
- If **no** `process` marker is present, the file is ignored by nemo-nb and treated as normal markdown.

This is what distinguishes a **markdown notebook** from a regular `.md` page.

### 1.3 Marker categories

We group markers as follows:

- **Essential markers** - you are likely to use these in most real notebooks.
- **Layout / syntax-sugar markers** - helpful for advanced layouts but not required.
- **Conversion / testing markers** - mainly for specialized workflows.

The rest of this file keeps the original, detailed marker reference with category notes added.

---

## 2. Marker commands reference

> The following sections are the detailed marker reference from the previous version of this document, with light edits to call out whether each marker is **essential**, **syntax sugar**, or **advanced**.

<!-- The large, existing reference content follows below. It has been preserved
     to remain LLM-friendly and exhaustive, while the short human-oriented docs
     live in the other markdown files. -->


<!-- BEGIN ORIGINAL DETAILED REFERENCE -->

Complete reference for all NeMo-NB marker commands and syntax.

---

## Overview

Marker commands control notebook structure and conversion behavior. There are two types of markers:

1. **Markdown Notebook Format Markers** - Define cell structure in `.md` source files
2. **Notebook Processing Markers** - Control conversion from notebooks to Sphinx docs

**Marker Format:**

```markdown
<!-- @nemo-nb: COMMAND [arguments] -->
```

For code cells in notebooks (not markdown format):

```python
# @nemo-nb: COMMAND [arguments]
// @nemo-nb: COMMAND [arguments]
```

---

## Markdown Notebook Format

Use these markers when authoring in markdown format (`.md` files that become notebooks).

### Cell Structure: Two Formats

**NeMo-NB supports TWO formats for code cells:**

#### Format 1: Triple Backticks (Recommended)

Use standard markdown fenced code blocks for code cells:

````markdown
# My Notebook

```python
x = 1
y = 2
```

More markdown text here.

```bash
echo "Hello"
```
<!-- @nemo-nb: output -->
Hello
````

**Key Points:**
- First cell is markdown by default (no marker needed)
- ````language` starts a code cell
- Markdown resumes after closing ``` fence
- Works with `<!-- @nemo-nb: output -->` markers
- More readable and standard markdown-compatible
- **Supports 4+ backticks**: Use ```````` to fence code containing ``` (standard markdown convention)

#### Format 2: Explicit Markers

Use explicit cell markers for more control:

```markdown
<!-- @nemo-nb: process -->
First cell is markdown by default.
<!-- @nemo-nb: cell python -->
print("This is a code cell")
<!-- @nemo-nb: output -->
This is a code cell
<!-- @nemo-nb: cell markdown -->
More markdown here (explicit markdown cell).
<!-- @nemo-nb: cell bash -->
echo "Another code cell"
<!-- @nemo-nb: output stream stderr -->
Error message here
```

**Key Points:**
- First cell is always markdown (no marker needed)
- `<!-- @nemo-nb: cell <language> -->` starts a code cell
- `<!-- @nemo-nb: cell markdown -->` starts a markdown cell (explicit)
- `<!-- @nemo-nb: output [type] [name] -->` adds output (optional)
- Newlines before markers are automatically removed
- Content continues until the next marker

#### Mixed Format

Both formats can be used in the same file:

```markdown
# Title

```python
x = 1
```

<!-- @nemo-nb: cell python -->
y = 2
<!-- @nemo-nb: output -->
Result: 2

```bash
echo "done"
```
```

#### Nested Fences (4+ Backticks)

If your code contains triple backticks, use four backticks to fence it (standard markdown):

````markdown
````python
# Code that contains triple backticks
example_code = """
```python
x = 1
```
"""
print(example_code)
````
````

**How it works:**
- Use ```````` (4+ backticks) as the fence delimiter
- Content inside can contain ``` without breaking the fence
- Automatically detected when converting notebooks to markdown

#### When to Use Each Format

**Use Triple Backticks** when:
- You want standard markdown formatting
- The notebook is simple (mostly code + markdown)
- You're authoring primarily in markdown
- Use 4+ backticks if code contains triple backticks

**Use Explicit Markers** when:
- You need explicit markdown cell boundaries
- You have complex output configurations
- You need literal fences inside markdown cells

---

## Command Categories

### Markdown Format Commands
- `cell` - **essential** for explicit cell boundaries.
- `output` - **optional**, for attaching explicit outputs.

### Essential Commands
- `process` - **essential**, enables conversion.
- `hide` - **essential but infrequent**, for hiding cells.

### Wrapping and Directives
- `wrap-cell-start` / `wrap-cell-end` - **common**, for tabs, dropdowns, admonitions.
- `insert` - **syntax sugar**, for inserting literal lines (options, labels, sync tags).
- `download` - **syntax sugar**, for adding a download link to the notebook.

### Indentation Control (syntax sugar)
- `multi-cell-indent-space-start` / `end`
- `multi-cell-indent-tab-start` / `end`
- `indent-space`
- `indent-tab`

### Code Block Control (syntax sugar)
- `language`
- `insert-code-block-start`

### Conversion Settings (advanced)
- `notebook-convert-4-space-to-tab`
- `disable-fence-conversion`

---

## Command Reference

> The following sections preserve the prior detailed descriptions for each marker (examples, behavior notes, etc.). They are intentionally verbose and optimized for deep understanding and LLM use.

<!-- The rest of the original reference content continues unchanged below. -->
