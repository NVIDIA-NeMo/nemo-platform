<!-- @nemo-nb: process -->
<!-- @nemo-nb: skip-test -->
<a id="about-jobs"></a>
# Safe Synthesizer Jobs

{{nss_short_name}} jobs orchestrate the complete pipeline from data preparation through synthesis to evaluation. Understanding the job lifecycle and configuration options is essential for effective use of the platform.

<!-- TODO: Link to generic {{platform_name}} jobs documentation when available for common job management concepts -->

## Job Lifecycle

A {{nss_short_name}} job progresses through several states:

### Job States

- **created**: Job has been created but not yet started
- **pending**: Job is queued and waiting for resources (GPU)
- **active**: Job is processing your data
- **completed**: Job finished successfully - results are ready
- **error**: Job encountered an error - check logs for details
- **cancelled**: Job was manually cancelled
- **cancelling**: Job is in the process of being cancelled
- **paused**: Job execution has been paused
- **pausing**: Job is in the process of being paused
- **resuming**: Job is resuming from a paused state

### Job Phases

A complete job typically includes these phases:

1. **Data Preparation**
 - Data validation and preprocessing
 - Column type inference
 - Grouping and ordering (if configured)
 - Train/test split for holdout evaluation

2. **PII Replacement** (optional)
 - PII detection using configured methods
 - Entity classification
 - Value transformation

3. **Synthesis**
 - **Training**: Fine-tune LLM on prepared data
 - Apply differential privacy (if enabled)
 - **Generation**: Generate synthetic records

4. **Evaluation**
 - Calculate SQS metrics
 - Calculate DPS metrics
 - Generate evaluation report

## Job Configuration

Jobs are configured through a hierarchical configuration structure:

### Top-Level Configuration

```python
{
    "name": "my-job",
    "project": "my-project",
    "spec": {
        "data_source": "fileset://default/safe-synthesizer-inputs/data.csv",
        "config": {
            # Configuration sections below
        },
    },
}
```

### Configuration Sections

- **data_prep**: Grouping, ordering, holdout configuration
- **replace_pii**: PII detection and replacement rules
- **training**: Model selection and training parameters
- **generation**: Synthetic data generation settings
- **privacy**: Differential privacy parameters
- **evaluation**: Quality and privacy assessment options

## Job Management

### Creating Jobs

Create jobs using:

- **Python SDK**: Recommended approach with `SafeSynthesizerJobBuilder`
- **REST API**: Direct HTTP requests for integration
- **CLI**: Command-line interface for scripting

### Monitoring Jobs

Track job progress through:

- **Status checks**: Poll job state
- **Logs**: View real-time execution logs
- **Events**: Subscribe to job state changes when supported by the deployment

### Retrieving Results

When the job completes, access:

- **Synthetic data**: Generated CSV files
- **Evaluation report**: HTML report with scores and visualizations
- **Metadata**: Job summary and configuration
- **Logs**: Complete execution history

## Job Builder API

The `SafeSynthesizerJobBuilder` provides a high-level interface for common workflows:

```python
import os
import pandas as pd

from nemo_platform import NeMoPlatform
from nemo_platform.beta.safe_synthesizer.job_builder import SafeSynthesizerJobBuilder

# Placeholders
df: pd.DataFrame = pd.DataFrame()
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

builder = (
    SafeSynthesizerJobBuilder(client)
    .with_data_source(df)
    .with_replace_pii()
    .synthesize()
)
job = builder.create_job(name="my-job", project="my-project")
```

The builder does the following:

- Uploads data to filesets automatically
- Provides smart defaults
- Validates configuration
- Returns a `SafeSynthesizerJob` instance for job interaction

## Best Practices

### Resource Planning

- Larger datasets and models require more GPU memory
- Training time scales with data size and model complexity
- Plan for 15-120 minutes for typical jobs

### Configuration

- Start with default settings
- Enable PII replacement for sensitive data
- Use differential privacy for maximum privacy guarantees
- Adjust generation parameters based on evaluation results

### Monitoring

- Check status periodically during execution
- Review logs if jobs fail or take longer than expected
- Use evaluation reports to iterate on configuration

### Error Handling

- Common errors: insufficient GPU memory, invalid data format, configuration errors
- Check logs for detailed error messages
- Reduce model size or data size if resource errors occur

## Troubleshooting

This section covers common issues and how to diagnose them.

### Viewing Job Logs

Logs are essential for diagnosing job failures. Access them through:

**Python SDK**:

```python
# Print logs to stdout
job.print_logs()

# Iterate over log entries programmatically
for log in job.fetch_logs():
    print(log.message.strip())
```

### Docker Compose Deployments

When running {{nss_short_name}} using Docker Compose, view container logs directly:

```bash
# View safe-synthesizer service logs
docker logs -f synthesis-test-20260114-051514-safe-synthesizer

# View logs with timestamps
docker logs -f --timestamps synthesis-test-20260114-051514-safe-synthesizer

# View last 100 lines
docker logs --tail 100 synthesis-test-20260114-051514-safe-synthesizer
```

To check the health status of containers:

```bash
docker ps
```

### Kubernetes Deployments

For Kubernetes deployments, use `kubectl` to access logs:

```bash
# List pods in your namespace
kubectl get pods -n <namespace>

# View logs for the safe-synthesizer pod
kubectl logs -f <pod-name> -n <namespace>

# View logs for a specific container in the pod
kubectl logs -f <pod-name> -c <container-name> -n <namespace>

# View previous container logs (if container restarted)
kubectl logs --previous <pod-name> -n <namespace>
```

To check pod status and events:

```bash
# Describe pod for detailed status and events
kubectl describe pod <pod-name> -n <namespace>

# Check events in the namespace
kubectl get events -n <namespace> --sort-by='.lastTimestamp'
```

### Common Issues and Solutions

#### Job Stuck in "Pending" State

**Symptoms:** Job remains in `pending` state for an extended period.

**Possible Causes:**

- No GPU resources available
- Resource quota exceeded
- Scheduling constraints not met

**Solutions:**

- Check available GPU resources in your cluster
- Verify resource quotas and limits
- Review pod events for scheduling failures

#### Out of Memory (OOM) Errors

**Symptoms:** Job fails with memory-related errors during training.

**Possible Causes:**

- Dataset too large for available GPU memory
- Batch size too high
- Model too large for available resources

**Solutions:**

- Reduce `batch_size` in training parameters
- Use a smaller subset of data for initial testing
- Increase `gradient_accumulation_steps` to maintain effective batch size with lower memory

#### Invalid Data Format Errors

**Symptoms:** Job fails during data preparation phase.

**Possible Causes:**

- CSV file has encoding issues
- Missing or malformed columns
- Unsupported data types

**Solutions:**

- Ensure CSV is UTF-8 encoded
- Validate column names do not contain special characters
- Check for null values or inconsistent data types

#### Generation Quality Issues

**Symptoms:** Generated synthetic data has poor quality or many invalid records.

**Possible Causes:**

- Insufficient training (low `num_input_records_to_sample`)
- Temperature too high or too low
- Data has complex patterns that need more training

**Solutions:**

- Increase `num_input_records_to_sample` for more training
- Adjust `temperature` (try 0.7-1.0 range)
- Enable `use_structured_generation` for better format adherence
- Review evaluation report for specific quality issues

## Related Topics

- [safe-synthesizer-101](../tutorials/safe-synthesizer-101.md): Get started with {{nss_short_name}} jobs
- [index](../tutorials/index.md): More hands-on tutorials
- [reference](reference.md): Full parameter reference
