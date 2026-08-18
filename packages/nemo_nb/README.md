<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# nemo-nb

`nemo-nb` is a Sphinx extension and CLI that make Jupyter-style notebooks work well as documentation.

It focuses on one idea:

- **You author executable examples as notebooks**, and
- **Sphinx renders them as clean MyST Markdown pages**, including tabs, dropdowns, and other directives.

At a glance:

- **Markdown notebooks, not plain `.md`**: The package works with *markdown notebooks* – notebook-like sources that eventually become `.ipynb` and then `.sphinx.md`. Plain narrative `.md` files are left alone.
- **Explicit opt‑in**: nemo-nb only processes files that contain the `nemo-nb: process` marker. No marker → no conversion.
- **Sphinx friendly**: Output is standard MyST Markdown with `sphinx-design` directives (tab-sets, dropdowns, etc.), ready for normal Sphinx builds.
- **CLI included**: You can convert between `.ipynb`, markdown‑notebook `.md`, and Sphinx‑docs `.sphinx.md` formats outside of Sphinx.

If you just want to *use* nemo‑nb:

- See **[AUTHORING_GUIDE.md](AUTHORING_GUIDE.md)** for how to write markdown notebooks and when nemo‑nb runs.
- See **[CLI.md](CLI.md)** for quick examples of the `nemo-nb` command.
- See **[USAGE.md](USAGE.md)** for common workflows and usage patterns in Sphinx docs.
- See **[INSTALL.md](INSTALL.md)** for installation instructions and Sphinx integration details.

For a full, detailed description of markers, file types, and advanced workflows, see **[MARKERS.md](MARKERS.md)** (the complete reference).
