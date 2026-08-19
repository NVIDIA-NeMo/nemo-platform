# OpenShell Harbor runtime handoff

## Goal

Keep Harbor datasets static. A dataset describes tasks, task files, metrics, and
the native Harbor dependency declaration; it does not contain OpenShell bridge
URLs, token environment-variable names, HTTP transports, or live sessions.

## Runtime boundary

`Evaluator.evaluation_runtime(dataset)` is the execution capability. Its
`dependency_context(task)` method is the only way analysis starts task
dependencies.

- Native Harbor starts the task's declared dependency runtime inside the
  evaluator boundary.
- Remote Harbor creates `RemoteHarborDependencyRuntime` only when that method
  is called. The runtime retains the existing start, execute, and stop behavior
  against the Harbor bridge.
- The evolutionary strategy passes this narrow capability to analysis.
- Rationalizer and Trace Analyzer use the capability when present, and retain
  `task.start_deps()` for evaluators that do not provide one.

## Main code paths

- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/evaluator/base.py`
  defines the evaluator-owned dependency context.
- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/evaluator/remote_harbor.py`
  adapts a static Harbor task to the bridge runtime on demand.
- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/evaluator/factory.py`
  constructs datasets without evaluator configuration.
- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/strategies/evolutionary.py`
  supplies the execution capability to analysis.
- `plugins/nemo-experimentalist/src/nemo_experimentalist_plugin/experimentalist/components/analyzer.py`,
  `rationalizer.py`, and `trace_analyzer.py` consume that capability.

## Artifact export

Bridge artifact export keeps approved resources under their path relative to
the bridge job work directory. It no longer assigns opaque numeric folders.
The bridge still exports only result-owned resources and rewrites host URIs.

## Tests

- `plugins/nemo-experimentalist/tests/test_harbor_bridge_service.py::test_job_api_exports_only_job_owned_artifacts`
  verifies preserved artifact paths without OpenShell, Docker, or TauBench.
- `plugins/nemo-experimentalist/tests/test_remote_harbor.py`
  verifies static Harbor datasets and evaluator-created remote runtimes with an
  in-process bridge.

## Follow-up

The shared typed `EvaluationRuntime` protocol exposes only
`dependency_context(task)`.
