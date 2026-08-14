<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# AUTHORING GUIDE (nemo-nb)

_Back to [README.md](README.md)._

This guide is intentionally short. It explains how to write **markdown notebooks** that nemo-nb will process during a Sphinx build.

---

## 1. What is a "markdown notebook"?

In this project, a **markdown notebook** is:

- A source file that is meant to behave like a Jupyter notebook (cells, outputs), and
- Something that nemo-nb will eventually turn into:
  1. an intermediate `.ipynb`, and then
  2. a `.sphinx.md` file that Sphinx reads.

It is **not** a generic narrative `.md` page. Plain `.md` files without the nemo-nb marker are treated as normal MyST docs and are **not** touched by nemo-nb.

---

## 2. The required opt-in marker

nemo-nb only processes files that explicitly opt in.

Add the marker **once** in your notebook source:

```markdown
<!-- @nemo-nb: process -->
```

or inside a code cell:

```python
# @nemo-nb: process
```

If this marker is missing:

- nemo-nb does **not** convert the file,
- no intermediate `.ipynb` or `.sphinx.md` is created for it, and
- Sphinx treats the page as a normal markdown document.

---

## 3. Basic authoring pattern (markdown notebook)

The simplest way to author is:

1. Start with markdown text.
2. Use fenced code blocks for code.
3. Add the `process` marker once.

Example:

````markdown
<!-- @nemo-nb: process -->
# Getting started

This is a markdown notebook. The code block below becomes a notebook cell.

```python
print("Hello, world!")
```
````

During the docs build, nemo-nb will:

1. Convert this markdown notebook into an `.ipynb` notebook.
2. Convert the notebook into a `.sphinx.md` file.
3. Let Sphinx render that `.sphinx.md` into HTML.

---

## 4. When to use markers

Most notebooks only need the `process` marker and normal fenced code blocks.

There are additional nemo-nb markers you can use to:

- wrap cells in `sphinx-design` directives (tab-sets, dropdowns),
- control indentation so code appears *inside* lists or directives,
- attach expected outputs, and
- add download links to the notebook (e.g., `<!-- @nemo-nb: download -->`).

Some of these markers are **core** (like `process` and basic cell markers), and many are **syntax sugar** for advanced layouts.

For everyday authoring you do **not** need to remember them all. Use:

- Standard markdown for prose,
- Fenced code blocks for examples,
- A single `process` marker to opt in.

When you need more control, see **`MARKERS.md`** for the complete marker reference.
