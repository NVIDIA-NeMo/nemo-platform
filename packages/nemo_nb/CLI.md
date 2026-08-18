<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# nemo-nb CLI (short guide)

_Back to [README.md](README.md)._

The `nemo-nb` command-line tool lets you convert between:

- **Markdown notebooks** (`.md` source that behaves like a notebook),
- **Jupyter notebooks** (`.ipynb`), and
- **Sphinx docs markdown** (`.sphinx.md`, ready for Sphinx).

This page gives only the essentials. For full CLI details and edge cases, see the CLI sections in **`MARKERS.md`**.

---

## 1. Verify the CLI

```bash
python3 -c "import nemo_nb; print(nemo_nb.__version__)"

nemo-nb --help
```

---

## 2. Common commands

### Markdown notebook → `.ipynb`

Use when you author in markdown and want a runnable notebook:

```bash
nemo-nb md-to-nb notebook.md
```

- Input: markdown notebook (`notebook.md`), usually containing `<!-- @nemo-nb: process -->`.
- Output: `notebook.ipynb` in standard Jupyter format.

### `.ipynb` → markdown notebook

Use when you start from a Jupyter notebook but want something easier to diff and review:

```bash
nemo-nb nb-to-md notebook.ipynb
```

- Output: `notebook.md` (markdown notebook format).

### Notebook → Sphinx docs markdown

Use to see what nemo‑nb will hand to Sphinx:

```bash
nemo-nb to-sphinx-md notebook.ipynb
```

- Output: `notebook.sphinx.md` with MyST directives, indentation, and markers applied.

---

## 3. When to use the CLI vs Sphinx

- **Sphinx build**: runs nemo‑nb automatically for any files that contain the `@nemo-nb: process` marker; you do **not** need the CLI in normal docs builds.
- **CLI**: use for local experiments, version‑control‑friendly workflows, or debugging conversion.

For advanced options (batch conversion, `--overwrite`, `--dry-run`, and error handling), see **`MARKERS.md`**.
