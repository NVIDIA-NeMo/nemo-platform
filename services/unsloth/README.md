# nmp-unsloth

Task package for **container-submit Unsloth SFT** under the NeMo Platform customization router.

This package owns the heavy code that runs *inside* the platform's GPU containers:

- **Canonical schemas** (`nmp.unsloth.schemas`) — `UnslothJobOutput` and shared sub-shapes consumed by both compile-time and runtime code.
- **Training driver** (`nmp.unsloth.tasks.training.backends.unsloth_sft.train_sft`) — runs SFT inside the training container's baked venv (`unsloth` + `torch` + `transformers` + `trl` + `peft` + `bitsandbytes`). Heavy imports are localized to the function body so the parent process can import this module without dragging in the ML stack.
- **Container entrypoints**:
  - `nmp.unsloth.tasks.file_io` — handles model + dataset download (pre-train) and checkpoint upload (post-train).
  - `nmp.unsloth.tasks.training` — runs `train_sft` against the paths the file_io step populated.
  - `nmp.unsloth.tasks.model_entity` — registers the output model entity / adapter.
- **Compile glue** (`nmp.unsloth.compile.platform_job_config_compiler`) — turns a canonical `UnslothJobOutput` into a 4-step `PlatformJobSpec`. Invoked by the plugin's `UnslothJob.compile`.

The thin contributor wrapper that registers Unsloth with the customization hub lives in `plugins/nemo-unsloth/`. That plugin owns submitter-facing schema (`UnslothJobInput`), the `UnslothContributor`, the `UnslothJob` lifecycle (`to_spec` + `compile`), the SDK shapes, and CLI overrides (`submit` reshaped, `run` disabled).

## Layout

```
services/unsloth/
├── pyproject.toml            # nmp-unsloth + [unsloth] extra for container image
├── README.md                 # this file
├── docker/                   # Dockerfile for nmp-unsloth-training
└── src/nmp/unsloth/
    ├── schemas.py            # canonical UnslothJobOutput + sub-shapes
    ├── compile.py            # public compile entry
    ├── config.py             # NMP_UNSLOTH_* env-var configuration
    ├── images.py             # image-ref resolution (nmp-unsloth-training etc)
    ├── download.py           # fileset download helper (sync)
    ├── upload.py             # fileset upload helper (sync)
    ├── model_entity.py       # output entity / adapter creation
    ├── platform_client.py    # async helpers for to_spec validation
    ├── app/
    │   ├── constants.py
    │   └── jobs/
    │       ├── compiler.py             # 4-step PlatformJobSpec builder
    │       ├── context.py              # NMPJobContext (env-var-driven)
    │       ├── file_io/schemas.py      # FileIOTaskConfig
    │       ├── model_entity/schemas.py # ModelEntityTaskConfig
    │       └── training/
    │           ├── compiler.py         # GPU training PlatformJobStep
    │           └── schemas.py          # TrainingStepConfig
    └── tasks/
        ├── file_io/__main__.py     + run.py
        ├── model_entity/__main__.py + run.py
        └── training/
            ├── __main__.py         (entrypoint: reads step config, calls train_sft)
            └── backends/
                └── unsloth_sft.py  (train_sft)
```

## Why a service package, not just a plugin module?

Two reasons:

1. **Container-process boundary.** The training driver and the file_io/model_entity tasks run inside containers built from this package. The plugin (compile-time) and the containers (runtime) need to share schemas (`UnslothJobOutput`, `FileIOTaskConfig`, `ModelEntityTaskConfig`, `TrainingStepConfig`) — co-locating them with the runtime code avoids a circular dep where the plugin owns canonical schemas the container needs to import.
2. **Image isolation.** The plugin process stays lightweight (no `unsloth` / `torch`). Heavy ML deps are installed only inside `nmp-unsloth-training` (see `docker/`).

## Status

Container submit is the **only** supported execution path. The GPU image (`docker/Dockerfile.nmp-unsloth-training`) installs the ML stack via the canonical `uv pip install unsloth --torch-backend=auto`, then layers the platform glue on top. The `[unsloth]` extra in `pyproject.toml` is now a thin alias for `unsloth[huggingface]` for any caller that wants to install the same ML stack outside the image.

See `docker/README.md` for build / push / GPU smoke-test instructions.
