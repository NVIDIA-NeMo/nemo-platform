<a id="eval-benchmarks-agentic"></a>
# Agentic Benchmarks

Evaluate agent tool-calling capabilities using industry-standard benchmarks.

## Prerequisites

Before running agentic benchmarks, ensure you have:

1. **Workspace**: Have a workspace created. All resources (metrics, secrets, jobs) are scoped to a workspace.

2. **Model endpoint**: A deployed model to evaluate for tool-calling capabilities.

3. **API key secrets** *(for some benchmarks)*: Some BFCL benchmarks require external API keys.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
```

---

## Berkeley Function Calling Leaderboard (BFCL)

BFCL is a benchmark for evaluating language model tool-calling capabilities. Use this evaluation type to benchmark tool-calling tasks using the [Berkeley Function Calling Leaderboard](https://gorilla.cs.berkeley.edu/leaderboard.html).

View all available BFCL benchmarks (`system/bfclv3-*`) with a label filter:

```python
bfcl_system_benchmarks = client.evaluation.benchmarks.list(
    workspace="system", extra_query={"filter[labels.eval_harness]": "bfcl"}
)
print(bfcl_system_benchmarks)
```

BFCL benchmark evaluation requires a model for online evaluation.

Some BFCL benchmarks call external APIs that require API keys (for example, `system/bfclv3-exec-*` benchmarks). Create secrets for the API keys before referencing them in the job.

- RapidAPI (free tier; subscription required): [Yahoo Finance](https://rapidapi.com/sparior/api/yahoo-finance15), [Real‑Time Amazon Data](https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-amazon-data), [Urban Dictionary](https://rapidapi.com/community/api/urban-dictionary), [COVID‑19](https://rapidapi.com/api-sports/api/covid-193), [Time Zone by Location](https://rapidapi.com/BertoldVdb/api/timezone-by-location)
- Direct APIs: [ExchangeRate‑API](https://www.exchangerate-api.com), [OMDb](http://www.omdbapi.com/apikey.aspx), [Geocode](https://geocode.maps.co/)

```python
client.secrets.create(
    workspace=workspace, name="rapid_api_key_secret", value="<your RapidAPI key>"
)
benchmark_params = {
    "rapid_api_key": "rapid_api_key_secret",
}
```

=== "Job"

    ```python
    from nemo_platform.types.evaluation import SystemBenchmarkOnlineJobParam

    job = client.evaluation.benchmark_jobs.create(
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/bfclv3-live-simple",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            benchmark_params={},
        )
    )
    ```
=== "Result"

    Accuracy of tool call predictions

    - Score name: tool-calling-accuracy
    - Value range: 0.0–1.0

    ```json
    {
      "scores": [
        {
          "name": "tool-calling-accuracy",
          "score_type": "range",
          "count": 1,
          "nan_count": 0,
          "sum": 1.0,
          "mean": 1.0,
          "min": 1.0,
          "max": 1.0,
          "std_dev": 0.0,
          "variance": 0.0
        }
      ]
    }
    ```
---

## Job Management

After creating a job, navigate to [Benchmark Job Management](job-management.md) to oversee its execution and monitor progress.

---

!!! info

    - [Agent Configuration](../metrics/agent-configuration.md) - Use agents (generic or NAT) as targets in online evaluation and benchmark jobs
    - [Agentic Evaluation Metrics](../metrics/agentic.md) - Detailed metric documentation for evaluating agentic workflows
    - [Managing Secrets](../../get-started/concepts/manage-secrets.md) - Store API keys for external APIs
    - [Evaluation Results](results.md) - Understanding and downloading results
