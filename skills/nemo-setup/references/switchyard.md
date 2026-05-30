# Switchyard Middleware

Load this reference when the user asks about routing, middleware, Switchyard, VirtualModels, or `nemo-switchyard` plugin loading.

`make bootstrap-python` and bare `uv sync` install `plugins/nemo-switchyard` through the workspace `enabled-plugins` group. The Switchyard library is vendored in-tree at `plugins/nemo-switchyard/vendor/switchyard/`; no separate checkout, `SWITCHYARD_PATH`, or PyPI workaround is needed.

Start with debug logging when investigating routing:

```bash
LOG_LEVEL=DEBUG uv run nemo services run \
  --services entities,models,inference-gateway,secrets \
  --controllers models
```

Middleware plugins load at platform startup. If a `VirtualModel` create fails with `422 references unknown plugin 'nemo-switchyard'`, restart services after bootstrap.
