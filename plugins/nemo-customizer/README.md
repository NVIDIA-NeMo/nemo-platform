# nemo-customizer

Router service for `/apis/customization`. Training backends (Automodel, RL, Megatron, …) register as **`nemo.customization.contributors`** entry points (discovered via `nemo_platform_plugin.discovery`).

Registers **`nemo.sdk`** → `customization` for `client.customization.*` (composes contributor SDK modules such as `client.customization.automodel.jobs`).

See [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) for contributor authoring.
