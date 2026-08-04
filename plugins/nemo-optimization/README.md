# nemo-optimization-plugin

Shared library for Fabric-backed numeric hyperparameter optimization (Optuna)
and the Agents ``optimize`` job implementation.

Primary user surface (Alt 5):

```bash
nemo agents optimize run|submit|explain
```

Golden-path agent shape: Fabric Hermes (``nvidia.fabric.hermes``). See
``examples/hermes-optimize/`` (``phishing.optimize.fabric-chatonly.yaml`` for a
proven CLI smoke; README covers the ``hermes-agent`` install workaround).

Per-task Fabric lifecycle hooks are author-supplied via string references
(``eval.run_hook.ref``, ``path``+``attr``, or ``nemo.fabric.task_hooks``
entry points) — see ``examples/hermes-optimize/hooks/``. The platform does
not vendor example-agent packages such as email phishing analyzer.

Job registration: ``agents.optimize`` (mounted by the agents plugin).
Backend registry: ``nemo.optimization.backends`` (``optuna``, ``ga`` stub).

This package is intentionally not a Customizer contributor. A future
Experimentalist / Customizer agent may call the same library.
