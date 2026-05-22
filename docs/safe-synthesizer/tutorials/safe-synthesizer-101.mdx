<!-- @nemo-nb: process -->
<!-- @nemo-nb: download -->
<a id="tutorial-safe-synthesizer-101"></a>
# Safe Synthesizer 101

Learn the fundamentals of {{nss_short_name}} by creating your first Safe Synthesizer job using provided defaults. In this tutorial, you'll upload sample customer data, replace personally identifiable information, fine-tune a model, generate synthetic records, and review the evaluation report.

## Prerequisites

Before you begin, make sure that you have:

- Access to a deployment of {{nss_short_name}} (see [getting-started](../getting-started.md))
- **An NVIDIA GPU with 80 GB+ VRAM** — Safe Synthesizer requires GPU access for model training, even when using remote inference for other services. Verify with `nvidia-smi`.
- Python environment with `nemo-platform` SDK installed
- Basic understanding of Python and pandas

---

## What You'll Learn

By the end of this tutorial, you'll understand how to:

- Upload datasets for processing
- Run Safe Synthesizer jobs using the Python SDK
- Track job progress and retrieve results
- Interpret evaluation reports

---

## Step 1: Install the SDK

Install the {{platform_name}} SDK with Safe Synthesizer support. Run the following command in a **terminal (shell)**:

```shell
if command -v uv &> /dev/null; then
 uv pip install nemo-platform[safe-synthesizer] kagglehub matplotlib
else
 pip install nemo-platform[safe-synthesizer] kagglehub matplotlib
fi
```

---

## Step 2: Configure the Client

Set up the client to connect to your Safe Synthesizer deployment:

```python
import os
from nemo_platform import NeMoPlatform

# Configure the client
client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
    access_token=os.environ.get("NMP_ACCESS_TOKEN"),
)
# set to none by default, update it if you need an hf_token
hf_secret_name = None

print("✅ Client configured successfully")
```

---

## Step 3: Verify Service Connection

Test the connection to ensure Safe Synthesizer is accessible:

```python
try:
    jobs = client.safe_synthesizer.jobs.list(workspace="default")
    print("✅ Successfully connected to Safe Synthesizer service")
    print(f"Found {len(jobs.data)} existing jobs")
except Exception as e:
    print(f"❌ Cannot connect to service: {e}")
    print("Please verify base_url and service status")
```

---

## Step 4: Load Sample Dataset

For this tutorial, we'll use a women's clothing reviews dataset from Kaggle that contains some PII:

```python
import pandas as pd
import kagglehub  # type: ignore[import-not-found]

# Download the dataset
path = kagglehub.dataset_download("nicapotato/womens-ecommerce-clothing-reviews")
df = pd.read_csv(f"{path}/Womens Clothing E-Commerce Reviews.csv", index_col=0)

print(f"✅ Loaded dataset with {len(df)} records")
print("\nDataset preview:")
print(df.head())
```

**Dataset details:**

- Contains customer reviews of women's clothing
- Includes age, product category, rating, and review text
- Some reviews contain PII like height, weight, age, and location

---

## Step 5: Configure Column Classification

Before running jobs, set up column classification for accurate PII detection.

!!! tip
    Column classification uses an LLM to automatically detect column types and improve PII detection accuracy. Without this setup, you may see classification errors and reduced detection quality.

--8<-- "_snippets/nvidia-build-model-provider.md"

```python
# Use the pre-configured NVIDIA Build model provider
# This provider is set up automatically during platform deployment
provider_name = "system/nvidia-build"
print(f"✅ Using model provider: {provider_name}")
```

!!! note
    If you prefer not to send column data to `build.nvidia.com`, you can [deploy your own LLM](../../run-inference/tutorials/deploy-models.md) and create a custom model provider. Pass the fully-qualified provider name (`workspace/provider-name`) to `.with_classify_model_provider()` instead.

---

## Step 6: HuggingFace Token Usage (Optional)

If you're using private HuggingFace models or want to avoid rate limits, create a secret for your [HuggingFace token](https://huggingface.co/settings/tokens):

```python
import os
import time

# Create a unique secret name (use hyphens, not underscores)
hf_secret_name = f"hf-token-{int(time.time())}"
hf_token = os.environ.get("HF_TOKEN")

if hf_token:
    # Store your HuggingFace token as a platform secret
    client.secrets.create(workspace="default", name=hf_secret_name, value=hf_token)
    print(f"✓ Created secret: {hf_secret_name}")
```

## Step 7: Create and Run a Safe Synthesizer Job

Use the `SafeSynthesizerJobBuilder` to configure and create a job:

```python
import pandas as pd
from nemo_platform.beta.safe_synthesizer.job_builder import SafeSynthesizerJobBuilder

# Create a project for our jobs (creates if it doesn't exist)
project_name = "test-project"
try:
    client.projects.create(workspace="default", name=project_name)
except Exception:
    pass  # Project may already exist

# Build the job configuration
job_name = f"synthesis-test-{pd.Timestamp.now().strftime('%Y%m%d-%H%M%S')}"
builder = (
    SafeSynthesizerJobBuilder(client)
    .with_data_source(df)
    .with_classify_model_provider(provider_name)  # Enable column classification
    .with_replace_pii()  # Enable PII replacement
    .synthesize()  # Enable synthesis
)

if hf_secret_name:
    # add the token secret if an HF token was specified
    builder = builder.with_hf_token_secret(hf_secret_name)

# Create and start the job
job = builder.create_job(name=job_name, project=project_name)
print(f"✅ Job created: {job.job_name}")
```

**What happens next:**

1. Dataset is uploaded to the fileset storage
2. PII detection and replacement
3. Model fine-tuning on your data
4. Synthetic data generation
5. Quality and privacy evaluation

---

## Step 8: Monitor Job Progress

Check the job status:

```python
status = job.fetch_status()
print(f"Current status: {status}")
```

**Job States:**

- `created`: Job has been created
- `pending`: Waiting for GPU resources
- `active`: Processing your data
- `completed`: Finished successfully
- `error`: Encountered an error

View real-time logs:

```python
job.print_logs()
```

Wait for completion (this may take 15-30 minutes depending on data size):

```python
print("⏳ Waiting for job to complete...")
try:
    job.wait_for_completion()
    print("✅ Job completed!")
except RuntimeError as e:
    print(f"❌ Job failed: {e}")
    raise
```

`wait_for_completion()` raises `RuntimeError` if the job ends in an `error` or `cancelled` state. Check the printed status output and logs above for the cause.

If the job fails with **"No GPUs available on this system"**, ensure your quickstart is configured with GPU access:

```bash
nemo quickstart configure
# Select "host-gpu" when prompted
nemo quickstart up
```

Verify GPU access with `nvidia-smi` on the host.

---

## Step 9: Retrieve Synthetic Data

Once the job is complete, retrieve the generated synthetic data:

```python
synthetic_df = job.fetch_data()

print(f"✅ Generated {len(synthetic_df)} synthetic records")
print("\nSynthetic data preview:")
print(synthetic_df.head())
```

Compare with original data structure:

```python
print("\n📊 Data Comparison:")
print(f"Original shape: {df.shape}")
print(f"Synthetic shape: {synthetic_df.shape}")
print(f"\nOriginal columns: {list(df.columns)}")
print(f"Synthetic columns: {list(synthetic_df.columns)}")
```

---

## Step 10: Review Evaluation Report

Fetch the job summary with high-level metrics:

```python
summary = job.fetch_summary()

print("📈 Evaluation Summary:")
print(f" Synthetic Quality Score: {summary.synthetic_data_quality_score}")
print(f" Data Privacy Score: {summary.data_privacy_score}")
print(f" Valid Records: {summary.num_valid_records}/{summary.num_prompts}")
```

Download the full HTML evaluation report:

```python
job.save_report("./evaluation_report.html")
print("✅ Evaluation report saved to evaluation_report.html")
```

If using Jupyter, display the report inline:

```python
job.display_report_in_notebook()
```

**The evaluation report includes:**

- **Synthetic Quality Score (SQS)**: Measures data utility
    - Column correlation stability
    - Deep structure stability
    - Column distribution stability
    - Text semantic similarity
    - Text structure similarity
- **Data Privacy Score (DPS)**: Measures privacy protection
    - Membership inference protection
    - Attribute inference protection
    - PII replay detection

---

## Understanding the Results

### Interpreting Scores

The evaluation report contains two high-level scores: Synthetic Quality Score (SQS) and Data Privacy Score (DPS). Both are measured out of 10, and higher is better. To learn more about how to interpret the scores, refer to the [evaluation guide](../about/evaluation.md).

---

## Next Steps

Now that you've completed your first Safe Synthesizer job, explore more advanced features:

### Advanced Tutorials

- [Differential Privacy Tutorial](differential-privacy.md) - Apply mathematical privacy guarantees

### Documentation

- [index](../about/index.md) - Understand core concepts

### Try These Next

1. **Customize PII replacement**: Configure specific entity types and replacement strategies
2. **Enable differential privacy**: Add formal privacy guarantees with epsilon and delta parameters
3. **Tune generation parameters**: Adjust temperature and sampling for better synthetic data
4. **Use your own data**: Replace the sample dataset with your sensitive data

---

## Cleanup

List and optionally delete completed jobs:

```python
# List all jobs
all_jobs = client.safe_synthesizer.jobs.list(workspace="default")
print(f"Total jobs: {len(all_jobs.data)}")

# Delete this job (optional)
# client.safe_synthesizer.jobs.delete(job.job_name, workspace="default")
# print(f"✅ Job {job.job_name} deleted")
```

---

## Troubleshooting

### Common Issues

**Connection errors:**

- Verify `NMP_BASE_URL` is correct
- Check that Safe Synthesizer service is running
- Ensure network connectivity

**Job failures:**

- Check logs with `job.print_logs()`
- Verify dataset format (CSV with proper columns)
- Ensure sufficient GPU memory for model size

**Slow performance:**

- Reduce dataset size for testing
- Use smaller model (adjust `training.pretrained_model`)
- Check GPU availability

For more help, see [jobs](../about/jobs.md).

**Error: "Dataset must have at least 200 records to use holdout."**

This occurs when synthesis is enabled on datasets with fewer than 200 records. Holdout validation
splits your data into training and test sets to measure quality, requiring a minimum dataset size.

**Solution:**

```python
builder = (
    SafeSynthesizerJobBuilder(client)
    .with_data_source(df)
    .with_data(holdout=0)  # Disable holdout for small datasets
    .with_replace_pii()
    .synthesize()
)
```

!!! warning
    Disabling holdout means you won't get quality metrics like privacy scores and synthetic data quality
    scores. For production use, ensure your dataset has at least 200 records.
