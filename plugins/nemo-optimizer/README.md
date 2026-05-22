# NeMo Optimizer Plugin

Empty scaffold for the `nemo-optimizer-plugin`. It is a valid installable
package that imports cleanly but does not register any services, CLIs, jobs,
controllers, middleware, or other surfaces with the NeMo Platform yet.

## Install

From the repository root:

```bash
uv pip install -e plugins/nemo-optimizer/
```

This plugin is intentionally **not** part of the `enabled-plugins` group in the
root workspace `pyproject.toml`, so it is not installed by `make
bootstrap-python` or a bare `uv sync`.

## Next steps

Add functionality by introducing the appropriate module under
`src/nemo_optimizer_plugin/` and wiring it through `[project.entry-points.*]`
in `pyproject.toml`. See `packages/nemo_platform_plugin/` for the plugin
contract and `plugins/example-plugin/` for a reference implementation of every
surface.
