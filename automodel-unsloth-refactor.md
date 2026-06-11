# Automodel & Unsloth — shared-code refactor

The Unsloth and Automodel customization backends each ship as **two packages**:

- **Plugin** (thin contributor wrapper): `plugins/nemo-unsloth/src/nemo_unsloth_plugin/`,
  `plugins/nemo-automodel/src/nemo_automodel_plugin/`
- **Service** (schemas, compiler, container task entrypoints): `services/unsloth/src/nmp/unsloth/`,
  `services/automodel/src/nmp/automodel/`

Both implement the same customization-contributor contract (`get_routers` / `get_cli` /
`get_authz_contribution` / `get_sdk_resources`, discovered by `nemo-customizer-plugin`) and the same
4-step container job flow: **download → train → upload → model-entity**. That overlap produced a large
amount of duplicated code, which this refactor pulls into one shared package.

---

## 1. Files that were common across plugin and service

These are the files that were duplicated (identical or near-identical) between the two backends and so
became candidates for sharing.

### Plugin side

| File | What was common |
|---|---|
| `sdk/http_utils.py`, `sdk/job_resources.py`, `sdk/resources.py` | The entire sync/async jobs-collection SDK client. Only the backend route segment (`unsloth` / `automodel`) and class-name prefix differ. |
| `contributor.py` | Same `get_routers` / `get_cli` / `get_authz_contribution` shape; differs only in name, help/tag strings, and the job class. |
| `cli/inputs.py`, `cli/main.py` | Same "disable `run`, re-register `submit` to take a positional `JOB_JSON`" override machinery; differs only in the input schema + a couple of help/error strings. |
| `config.py` | Same plugin settings (`default_training_execution_profile`) and the `generate_<svc>_id()` job-name helper. |
| `jobs/jobs.py` | Same `NemoJob` `to_spec` + Docker-runtime guard. (`compile()` genuinely diverges and stays per-backend.) |
| `transform.py` | Same output-name generation (slugify + basename + random suffix). (The input→output assembly is schema-bound and stays per-backend.) |

### Service side

| File | What was common |
|---|---|
| `platform_client.py` | `check_dataset_access` + `fetch_model_entity`. |
| `app/jobs/context.py` | `NMPJobContext` env-var loader. |
| `app/jobs/file_io/schemas.py` | file_io task config + `FileSetRef` + error/stat types. |
| `app/constants.py` | Container-path constants (model/dataset/output dirs) + job URL env vars. |
| `entities/values.py` | `FinetuningType`, `OutputNameType` (identical). |
| `images.py` | Docker image registry-resolution helper. |
| `tasks/file_io/utils.py` | Fileset path/IO + SDK error-handling helpers. |
| `tasks/file_io/progress_reporter.py`, `tasks/progress_reporter.py` | file_io progress reporting (`JobsServiceProgressReporter`, `NoOpProgressReporter`). |
| `tasks/training/progress.py` | Training `JobsServiceProgressReporter` (high-level phase reporting). |
| `tasks/training/backends/callbacks.py` | `TrainingProgressCallback` (loss/checkpoint reporting). |
| `tasks/file_io/run.py`, `tasks/model_entity/run.py` | `FileIORunner` / `ModelEntityRunner` (near-identical, 400–500 lines each). |
| `app/jobs/compiler.py` | The 4-step compiler skeleton + CPU-resource/base-env helpers. |

### Stayed per-backend (genuinely diverged — not shared)

- `schema.py` and `app/jobs/training/{schemas,compiler}.py` — the two backends accept different training
  parameters (this is the surface targeted by §4's parameter-unification follow-ups).
- `compile.py` adapter logic and the bulk of `app/jobs/compiler.py` bodies (Automodel adds teacher-model
  download, deployment-config validation, tool-calling metadata, embedding gating).
- All Automodel-only training modules (`adapter.py`, `tasks/training/backends/*`,
  `tasks/training/{datasets,errors,model_utils}/*`, etc.).

---

## 2. Refactor design — one shared package

All shared code lives in a single new package, **`nmp-customization-common`**, and each backend keeps a
thin shim/subclass at its original import paths.

### The package

| | |
|---|---|
| **Path** | `packages/nmp_customization_common` |
| **Distribution** | `nmp-customization-common` |
| **Namespace** | `nmp.customization_common` (ships `src/nmp/`, **no `src/nmp/__init__.py`** — PEP 420, mirroring `nmp_common`) |
| **Depends on** | `nmp-common`, `nemo-platform-sdk`, `nemo-platform-plugin` |
| **Entry points** | none — discovery stays on the concrete plugins |

**Why one package (not separate plugin/service libs):** both layers already cross-depend
(the services import `nemo_platform_plugin`; the plugins pull the service deps transitively), and a
single wheel can host both layers as submodules — so one package is simpler and matches repo convention.
It belongs to the `nmp-*` family because it ships into the shared `nmp.*` namespace alongside
`nmp.common` / `nmp.unsloth` / `nmp.automodel`.

### Install model (works when only one plugin is installed)

This is a `uv` workspace. The dependency chain is:

```
nemo-<svc>-plugin ──▶ nmp-<svc> (service) ──▶ nmp-customization-common
nemo-<svc>-plugin ──────────────────────────▶ nmp-customization-common   (also direct, for the plugin bases)
```

Because `nmp-customization-common` is a normal `dependencies` entry on all four consumers, it's pulled in
**transitively** whenever a backend is installed. Installing only `nemo-unsloth-plugin` brings it in via
`nmp-unsloth`. No meta-package, no extras, no special handling.

**Wiring:** add `packages/nmp_customization_common` to the root `[tool.uv.workspace] members` and
`nmp-customization-common = { workspace = true }` to `[tool.uv.sources]`; add the dependency (and the
workspace source) to both plugins and both services.

### How each backend shrinks

The shared package provides bases/helpers; each backend keeps a small file at the **contract path** that
subclasses or re-exports them. The symbols that must stay put (they are imported by entry points and by
the customizer SDK hub):

- `nemo_<svc>_plugin.contributor:<Svc>Contributor` — `nemo.customization.contributors` entry point.
- `nemo_<svc>_plugin.jobs.jobs:<Svc>Job` — `nemo.jobs` entry point.
- `nemo_<svc>_plugin.sdk.resources:{<Svc>Customization, Async<Svc>Customization}` — returned by the
  contributor's `get_sdk_resources()` and composed under `client.customization.<svc>`.

The package is organized by domain:

```
nmp/customization_common/
  version.py
  sdk/         client.py          # make_customization_sdk factory (jobs-collection SDK)
  cli/         overrides.py       # apply_job_cli_overrides (run/submit machinery)
  contributor/ base.py            # BaseContributor (get_routers/get_cli/get_authz/get_sdk_resources)
               config.py          # BaseTrainingPluginConfig + generate_job_id
               jobs.py            # BaseSubmitJob + require_docker_runtime (to_spec + Docker guard)
               transform.py       # slugify / random_suffix / *_basename / generated_output_name
  schemas/     file_io.py  model_entity.py  integrations.py  values.py
  training/    progress.py        # JobsServiceProgressReporter (high-level phase reporting)
               callbacks.py       # TrainingProgressCallback
  tasks/       file_io_utils.py   file_io_progress_reporter.py
  service/     constants.py  context.py  images.py  platform_client.py
```

- **`sdk` / `cli` / `contributor`** are the plugin-side bases (imported by the `nemo_<svc>_plugin`
  modules). Each `<Svc>Contributor` subclasses `contributor.base.BaseContributor`, supplying class
  attributes (`name`, `job_cls`, `cli_help`, …) and a `get_sdk_resources` override; `compile()` is
  overridden per backend on `contributor.jobs.BaseSubmitJob`.
- **`schemas`** holds the shared pydantic models / enums used by both layers.
- **`training` / `tasks` / `service`** are service-side (imported by `nmp.<svc>`): progress reporting +
  training callbacks, file_io task helpers, and the job context / platform client / path constants /
  image resolution.


The two backends converge on a shared, opinionated training-parameter surface so a job spec means the
same thing on both:

- **Integrations object** — one shared `nmp.common.integrations` schema (`IntegrationsSpec` / `WandbIntegration`).
- **Epoch behavior** — `epochs` defaults to `1` on both (Unsloth's old epochs/max_steps mutex removed).
- **Steps behavior** — `max_steps`, when set, caps/overrides epochs on both.
- **All-weights / full naming** — Unsloth's finetuning type is now `all_weights` (was `full`).


---

## 3. Implementaion

Implemented in `packages/nmp_customization_common/`; each backend reduced to thin shims/subclasses at the
original import paths. Verified: plugin + customizer suites and both service suites pass per-service;
`ruff` and `ty` clean on the package.


- **Shared package** scaffolded and wired into the workspace + all four consumers (transitive install verified).
- **Plugin SDK** collapsed into `sdk.make_customization_sdk`; per-plugin `sdk/resources.py` are shims.
- **Plugin bases** — `BaseContributor`, `apply_job_cli_overrides`, `BaseTrainingPluginConfig` +
  `generate_job_id`, `BaseSubmitJob` + `require_docker_runtime`. Reconciled with the upstream
  `get_sdk_resources()` contributor contract.
- **Transform helpers** shared (`slugify` etc.); Automodel now slugifies generated names like Unsloth.
- **Service modules** — `context`, `platform_client`, `constants`, `values`, `images`, `file_io_schemas`,
  `file_io_utils`, `file_io_progress_reporter`, `training_progress`, `training_callbacks`, and the
  `model_entity` step schema extracted; backends re-export/subclass.
- **Opinionated shared training parameters** (PR-review items):
  - **Integrations object** — one shared `IntegrationsSpec` / `WandbIntegration`
    (`nmp.common.integrations`); runtime helpers in `nmp.customization_common.integrations`.
  - **Epoch behavior** — Unsloth now matches Automodel: `epochs` defaults to `1` (the old
    epochs/max_steps mutex is removed).
  - **Steps behavior** — `max_steps`, when set, caps/overrides epochs on both backends (trl semantics).
  - **All-weights / full naming** — Unsloth's finetuning type is now `all_weights` (was `full`),
    matching Automodel. (Unsloth is unreleased, so this is a safe rename.)
- **Image resolution** — Unsloth ships a single image, so `get_tasks_image()` returns the training image
  (`nmp-unsloth-training`); the CPU task steps reuse it. (No `nmp-unsloth-tasks` image is built.)
- **Cleanup** — removed empty license-only `__init__.py` files (kept the `run`-re-exporting ones that
  back the `python -m nmp.<svc>.tasks.<x>` container entrypoints).

---

## 4. Follow-ups

- **Shared task runners** — extract `tasks/file_io/run.py` (`FileIORunner`) and
  `tasks/model_entity/run.py` (`ModelEntityRunner`) to shared bases. Near-identical (~400–500 lines each);
  backends supply only a `SERVICE_SOURCE` string / task-config types, and the model_entity runner needs
  Automodel restructured to match Unsloth's LoRA/full helper split first.
- **Shared compiler scaffold** — only the 4-step skeleton + `_get_cpu_resources` / `_get_base_environment`
  helpers are common; the bodies diverge heavily (Automodel ~502 lines vs Unsloth ~292). Extract the
  skeleton with abstract hooks only if the value justifies touching the most correctness-critical file.
