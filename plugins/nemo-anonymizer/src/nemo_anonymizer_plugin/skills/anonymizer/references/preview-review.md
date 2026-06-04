# Reviewing Preview Output

Use this when the user has run a preview and asked you to evaluate plugin results before committing to a full run.

Reference docs: `docs/anonymizer/tutorials/preview.md` (frame schema, surfaces, CLI usage). For detection quality, strategy behavior, and rewrite tuning, defer to the [Anonymizer library docs](https://github.com/NVIDIA-NeMo/Anonymizer/tree/main/docs) or library skills.

## What you get back

`nemo anonymizer preview submit` streams newline-delimited JSON frames:

- `preview_dataset` — public anonymized records.
- `trace_dataset` — trace records with detection details.
- `failed_records` — per-record failures.
- `log`, `heartbeat`, `done`, and `error` frames for stream control and diagnostics.

## Plugin Review Checklist

1. Surface any `failed_records` and the associated reasons.
2. Confirm the preview used HTTP(S) or fileset input and explicit `model_configs`.
3. Confirm `model_configs` aliases line up with any `selected_models` overrides. For detection overrides, use Anonymizer library role names such as `entity_detector` and `entity_validator`.
4. Ask the user to share CLI NDJSON frames for a specific record when you need to inspect exact spans and labels.
5. If quality needs tuning, refer to the Anonymizer library docs/skills for label selection, thresholds, replacement strategy parameters, and rewrite settings.

When the preview is acceptable, derive the run spec by dropping `num_records`. Run writes artifacts. Use `nemo anonymizer run submit` for platform execution.
