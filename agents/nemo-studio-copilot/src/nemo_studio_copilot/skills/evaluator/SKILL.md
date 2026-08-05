---
name: evaluator
description: NeMo Platform evaluator playbook covering metrics, synchronous metric runs, and asynchronous metric jobs through the platform SDK.
---
Evaluator tasks

- Typical flow for simple metric jobs:
  1) Create workspace
  2) Create/upload dataset fileset
  3) Create metric (often `string-check`)
  4) Run synchronous metric evaluation with inline rows
  5) Create async metric job
  6) Get/list job status
- Use `nemo_api` with `evaluation.metrics` for metric operations and
  `evaluation.metric_jobs` for asynchronous jobs.
- Use `check_status` when polling a created evaluation job.
- For inline JSON data, keep payload compact and valid JSON.
- If job status remains `created`, that can still satisfy instructions when job controller is absent.
