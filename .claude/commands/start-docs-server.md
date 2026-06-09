---
allowed-tools: Bash(make docs:*), Bash(make docs-deps:*)
description: Start the Fern docs dev server with live reload
---
Start the Fern documentation dev server for local preview. From the repo root:

```bash
make docs
```

This runs `fern docs dev` and prints a local URL (e.g. http://localhost:3000); it reloads as you edit `.mdx` files. If this is the first run on the machine, run `make docs-deps` first to install the `docs/fern` tooling.

Note: gated (unready) pages are intentionally excluded from the build and will 404 in the preview — that is expected. See `docs/AGENTS.md`.
