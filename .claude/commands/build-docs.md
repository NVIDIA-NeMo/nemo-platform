---
description: Build / validate the Fern documentation
---
The docs are built with Fern (not MkDocs). From the repo root:

1. **Validate** (what CI runs — `fern check` + MDX validation + gated-link check):
   ```bash
   make docs-check
   ```

2. **Check for broken links:**
   ```bash
   make docs-broken-links
   ```

First run on a machine needs `make docs-deps` (installs `docs/fern` tooling).

To preview locally with live reload, use `/start-docs-server` (`make docs`). The published site is built by the `Publish Fern Docs` workflow on push to `main`. See `docs/AGENTS.md` and `docs/fern/README.md`.
