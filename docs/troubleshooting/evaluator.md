<a id="evaluator-troubleshooting"></a>
# Troubleshooting Evaluator

Use this documentation to troubleshoot issues that can arise when you work with the [Evaluator plugin](../evaluator/index.md).

!!! tip
    For durable evaluator jobs, use the returned job resource to wait for completion and download artifacts. See [Metric Job Management](../evaluator/metrics/job-management.md).

---

<a id="unsupported-judge-model"></a>
## Unsupported Judge Model

LLM-as-a-Judge evaluates the quality of another model's output using an evaluation prompt and scoring criteria. The prompt applies structure to the judge's output, which is then parsed to generate metric scores.

Not all models make good judges. If the judge produces inconsistent output or does not follow the expected format, the evaluation can fail with parsing errors. This is commonly observed for smaller models.

```
The output string did not satisfy the constraints given in the prompt.
Please return the output in a JSON format that complies with the schema.
```

Use a stronger judge model, simplify the rubric, or test locally with `client.evaluator.run(...)` before submitting a durable job.

## Dataset Reference Cannot Be Resolved

If a job fails before evaluation starts, verify that the dataset reference is available to the execution mode you selected:

- Local runs can use inline rows or local paths that exist in the current process.
- Durable platform jobs can use inline rows or platform `FilesetRef` values.
- Fileset paths must point at files that exist in the Files service for the selected workspace.

If the error says the datastore is unavailable, verify that the Files service is reachable. If the datastore is reachable but the file is missing, upload or re-register the fileset before resubmitting the job.

## Error Connecting to Inference Server

This means the evaluator could not reach the model, agent, or judge endpoint used by the metric.

Check that the endpoint URL is reachable from the job runtime, that any required API key is available, and that the model name matches the endpoint provider. For durable jobs, use a platform secret name in `api_key_secret`; for local runs, make sure the matching environment variable is exported.

## Inference SSL Error

An evaluation job that uses an HTTPS model endpoint can fail if the endpoint certificate or DNS name is not trusted by the local environment. Verify that the model URL is reachable from the host running {{platform_name}} and that the endpoint presents a valid certificate for its hostname.

```
HTTPSConnectionPool(host="<model endpoint>", port=443): Max retries exceeded with url: /v1/chat/completions (Caused by SSLError)
```

## Evaluation Job Takes a Long Time

Evaluation job duration depends on dataset size, target model latency, judge latency, and `RunConfig(parallelism=...)`. As long as the status is `RUNNING`, the job is still active.

If a job is unexpectedly slow, lower the dataset size with `RunConfig(limit_samples=...)`, increase `parallelism` only within the model endpoint's rate limits, or run a small local sample first with `client.evaluator.run(...)`.

## Advanced Troubleshooting

To troubleshoot a failed durable job, download the job artifacts and inspect the generated logs and result files:

```python
job = client.evaluator.get_job_resource("my-job-name")
artifacts_dir = job.download_artifacts(path="evaluation_artifacts")
print(artifacts_dir)
```

The artifacts directory contains the runtime files produced by the evaluator plugin job, including logs when the job runtime emitted them.
