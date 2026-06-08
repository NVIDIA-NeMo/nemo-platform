# Add A Custom Surface-Adherence Metric

Use the `nemo-evaluator-plugin` skill to produce a runnable standalone Evaluator SDK metric example.
Read the skill before writing the solution.

Create `/workspace/output/surface_adherence_metric.py`. The script must use the local standalone
Evaluator SDK from `packages/nemo_evaluator_sdk` in the checked-out repo context.

Use only `packages/nemo_evaluator_sdk` and SDK-level APIs in your answer. Do not propose the
`nemo` CLI, plugin SDK APIs, or any `services/*` implementation path.

`/workspace/output/surface_adherence_metric.py` must include:

- The package/path `packages/nemo_evaluator_sdk`.
- A zero-argument metric class compatible with the SDK `Metric` protocol, including a `type` property.
- The current SDK symbols `Metric`, `MetricInput`, `MetricOutput`, `MetricOutputSpec`, `MetricResult`, `output_spec`, and `compute_scores`.
- Row-level outputs named `surface_adherence` and `surface_violation_count`.
- Logic that reads `observed_surfaces`, `allowed_surfaces`, and `forbidden_surfaces` from `input.row.data`.
- Treatment of `observed_surfaces` as the integration surfaces the evaluated path actually used, `allowed_surfaces` as the surfaces permitted for the task, and `forbidden_surfaces` as surfaces that should always count as violations.
- `surface_adherence` as a numeric score where `1.0` means all observed surfaces are allowed and no forbidden surfaces were used, and lower values indicate violations.
- `surface_violation_count` as the number of observed surfaces that are forbidden or outside the allowed set.
- A passing example where `observed_surfaces=["standalone_sdk"]` and `allowed_surfaces=["standalone_sdk"]` produces `surface_adherence=1.0` and `surface_violation_count=0`.
- A failing example where `observed_surfaces` includes `legacy_service` and `forbidden_surfaces=["legacy_service"]` produces `surface_adherence=0.0` or another penalty below `1.0`, with `surface_violation_count` greater than `0`.

Your final answer should be a short summary only.
