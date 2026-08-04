# nemo-optimization-plugin

Shared library for Fabric-backed numeric hyperparameter optimization (Optuna)
and the Agents ``optimize`` job implementation.

Primary user surface (Alt 5):

```bash
nemo agents optimize run|submit|explain
```

Golden-path agent shape: Fabric Hermes (``nvidia.fabric.hermes``). See
``examples/hermes-optimize/``.

Job registration: ``agents.optimize`` (mounted by the agents plugin).
Backend registry: ``nemo.optimization.backends`` (``optuna``, ``ga`` stub).

This package is intentionally not a Customizer contributor. A future
Experimentalist / Customizer agent may call the same library.
