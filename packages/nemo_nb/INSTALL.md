<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Installing and enabling nemo-nb

_Back to [README.md](README.md)._

`nemo-nb` is a Python package that lives inside this repository but is **not**
installed into the root virtual environment by default.

There are two common ways it is installed:

- **Docs virtual environment**: when you create and use the `docs/` virtual
  environment (for example via the docs build tooling), `nemo-nb` is installed
  there automatically as part of the docs toolchain.
- **CLI usage in your own environment**: if you want to use the `nemo-nb` CLI
  from a virtual environment outside of `docs/`, you must install the package
  manually from the repository root:

  ```bash
  uv pip install -e packages/nemo_nb
  ```

Once `nemo-nb` is installed in the environment where Sphinx runs, you mainly
need to ensure it is enabled in Sphinx and that you understand when it runs.

---

## 1. Sphinx configuration

In your `conf.py`:

```python
extensions = [
    "myst_parser",   # MyST markdown
    "sphinx_design", # Tabs, dropdowns, grids
    "nemo_nb", # Notebook processing
]

# Optional future configuration
nemo_nb_config = {}
```

- `myst_parser` and `sphinx_design` provide the markdown and layout primitives.
- `nemo_nb` wires in the two‑stage notebook conversion.

---

## 2. What nemo-nb will (and will not) process

nemo‑nb only processes files that explicitly opt in with the marker:

```markdown
<!-- @nemo-nb: process -->
```

or in a code cell:

```python
# @nemo-nb: process
```

Effects:

- Files **with** the marker are treated as **markdown notebooks**.
  - nemo‑nb may generate intermediate `.ipynb` and `.sphinx.md` for them.
- Files **without** the marker are treated as normal MyST `.md` files; nemo‑nb does **nothing**.

This keeps narrative docs and test fixtures separate from notebook‑style content.

---

## 3. Building docs

Once `conf.py` is configured:

```bash
sphinx-build -b html docs _build/html
```

During the build, nemo‑nb:

1. Finds any opted‑in markdown notebooks.
2. Converts them to `.ipynb`.
3. Converts those notebooks to `.sphinx.md` for Sphinx.

For a deeper look at the processing pipeline, markers, and CLI integration, see **`MARKERS.md`**.
