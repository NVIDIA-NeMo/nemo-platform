<!-- @nemo-nb: process -->
<!-- @nemo-nb: download -->
<a id="data-designer-tutorials-basics"></a>
# The Basics

This tutorial demonstrates the fundamentals of Data Designer by generating a product review dataset.

For more detail about column behavior, see the [open-source library's version](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/tutorials/the-basics) of this tutorial.

## Prerequisites

Ensure you have completed the [tutorials prerequisites](index.md#prerequisites). This tutorial uses an Inference Gateway provider, so local CLI `run` and NeMo Services execution both need access to the Inference Gateway API in a running NeMo Services cluster.

## Part 1: Build the Configuration

Use the `data_designer.config` package to define your dataset schema. This configuration code is the same across the plugin execution modes.

!!! tip
    Build the configuration once, then choose whether to execute with CLI `run`, CLI `submit`, or the SDK.

### Define Models

Start by defining the models you want to use:

```python
import data_designer.config as dd

MODEL_ALIAS = "text"

model_configs = [
    dd.ModelConfig(
        provider="default/nvidia-build",
        model="nvidia/nemotron-3-nano-30b-a3b",  # Use the `served_model_name` from the provider
        alias=MODEL_ALIAS,
        inference_parameters=dd.ChatCompletionInferenceParams(
            temperature=1.0,
            top_p=1.0,
        ),
    )
]

config_builder = dd.DataDesignerConfigBuilder(model_configs)
```

### Add Columns

Define the columns for your dataset. The [library documentation](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/tutorials/the-basics) explains these column types in detail.

{% raw %}
```python
# Product category sampler
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="product_category",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=[
                "Electronics",
                "Clothing",
                "Home & Kitchen",
                "Books",
                "Home Office",
            ],
        ),
    )
)

# Product subcategory sampler (conditional on category)
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="product_subcategory",
        sampler_type=dd.SamplerType.SUBCATEGORY,
        params=dd.SubcategorySamplerParams(
            category="product_category",
            values={
                "Electronics": [
                    "Smartphones",
                    "Laptops",
                    "Headphones",
                    "Cameras",
                    "Accessories",
                ],
                "Clothing": [
                    "Men's Clothing",
                    "Women's Clothing",
                    "Winter Coats",
                    "Activewear",
                    "Accessories",
                ],
                "Home & Kitchen": [
                    "Appliances",
                    "Cookware",
                    "Furniture",
                    "Decor",
                    "Organization",
                ],
                "Books": [
                    "Fiction",
                    "Non-Fiction",
                    "Self-Help",
                    "Textbooks",
                    "Classics",
                ],
                "Home Office": [
                    "Desks",
                    "Chairs",
                    "Storage",
                    "Office Supplies",
                    "Lighting",
                ],
            },
        ),
    )
)

# Target age range
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="target_age_range",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=["18-25", "25-35", "35-50", "50-65", "65+"]
        ),
    )
)

# Customer details using Faker
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="customer",
        sampler_type=dd.SamplerType.PERSON_FROM_FAKER,
        params=dd.PersonFromFakerSamplerParams(age_range=[18, 70], locale="en_US"),
    )
)

# Star rating
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="number_of_stars",
        sampler_type=dd.SamplerType.UNIFORM,
        params=dd.UniformSamplerParams(low=1, high=5),
        convert_to="int",  # Convert the sampled float to an integer
    )
)

# Review style
config_builder.add_column(
    dd.SamplerColumnConfig(
        name="review_style",
        sampler_type=dd.SamplerType.CATEGORY,
        params=dd.CategorySamplerParams(
            values=["rambling", "brief", "detailed", "structured with bullet points"],
            weights=[1, 2, 2, 1],
        ),
    )
)

# LLM-generated product name
config_builder.add_column(
    dd.LLMTextColumnConfig(
        name="product_name",
        prompt=(
            "You are a helpful assistant that generates product names. DO NOT add quotes around the product name.\n\n"
            "Come up with a creative product name for a product in the '{{ product_category }}' category, focusing "
            "on products related to '{{ product_subcategory }}'. The target age range of the ideal customer is "
            "{{ target_age_range }} years old. Respond with only the product name, no other text."
        ),
        model_alias=MODEL_ALIAS,
    )
)

# LLM-generated customer review
config_builder.add_column(
    dd.LLMTextColumnConfig(
        name="customer_review",
        prompt=(
            "You are a customer named {{ customer.first_name }} from {{ customer.city }}, {{ customer.state }}. "
            "You are {{ customer.age }} years old and recently purchased a product called {{ product_name }}. "
            "Write a review of this product, which you gave a rating of {{ number_of_stars }} stars. "
            "The style of the review should be '{{ review_style }}'. "
            "Respond with only the review, no other text."
        ),
        model_alias=MODEL_ALIAS,
    )
)
```
{% endraw %}

## Part 2: Execute

Now execute your configuration. You can run locally through the CLI, submit to NeMo Services, or call the Data Designer API from the SDK.

### Local CLI Execution

Save the configuration in a Python file such as `product_reviews.py` and expose a `load_config_builder()` function that returns the `config_builder`.

```python
def load_config_builder() -> dd.DataDesignerConfigBuilder:
    return config_builder
```

Preview locally:

```bash
nemo data-designer preview run product_reviews.py --num-records 5
```

Generate a larger dataset locally:

```bash
nemo data-designer create run product_reviews.py --num-records 30
```

This workload runs in the local CLI process, but because the configuration references `default/nvidia-build`, it still communicates with the Inference Gateway API.

### NeMo Services CLI Execution

Submit the same configuration to NeMo Services when you want service-managed execution:

```bash
nemo data-designer preview submit product_reviews.py --workspace default --num-records 5
nemo data-designer create submit product_reviews.py --workspace default --profile default --num-records 30
```

### SDK Data Designer API Execution

The `DataDesignerResource` is your SDK interface for Data Designer API execution. You can access it from an existing SDK instance:

```python
import os
from nemo_platform import NeMoPlatform

base_url = os.environ.get("NMP_BASE_URL", "http://localhost:8080")
client = NeMoPlatform(base_url=base_url, workspace="default")

data_designer = client.data_designer
```


### Previewing the Dataset

Use the `preview` method for API-backed rapid iteration. Generate a small sample, inspect the results, adjust your configuration, and repeat:

```python
preview = data_designer.preview(config_builder)

# Display a random sample record
preview.display_sample_record()

# Access the full preview dataset as a pandas DataFrame
df = preview.dataset
print(df.head())

# View statistical analysis
preview.analysis.to_report()
```

--8<-- "data-designer/_snippets/preview-results.md"

**Iterate:** Adjust column configurations, prompts, or parameters in your `config_builder`, then run `preview` again until you're satisfied with the results.

### Scaling Up with Jobs

When you're happy with the preview, create a larger service-managed generation job:

```python
# Defaulting to 30 for demo speed purposes. Happy with the output? Scale it up!
job = data_designer.create(config_builder, num_records=30)

# Block until the job completes
job.wait_until_done()

# Download the generated artifacts
results = job.download_artifacts()

# Load the dataset as a pandas DataFrame
dataset = results.load_dataset()
print(dataset.head())

# Load the full analysis report
analysis = results.load_analysis()
analysis.to_report()
```

--8<-- "data-designer/_snippets/job-results.md"

## What Happens Under the Hood

When you use CLI `run`:

1. **Local Execution:** The Data Designer workload runs in the CLI process.
2. **Resource Resolution:** The workload can use local resources, NeMo resources, or both.
3. **Generation:** Data Designer resolves dependencies and generates records in the local environment.

When you use CLI `submit` or the SDK today:

1. **Configuration Validation:** The service validates your configuration and resolves column dependencies
2. **NeMo Services Execution:** Preview runs through the Data Designer API; create runs as a service-managed job
3. **Inference Routing:** LLM calls are routed through Inference Gateway to your configured model providers
4. **Artifact Storage:** Job datasets and analysis reports are stored in job artifact storage
5. **Job Completion:** You can monitor job status and load results when complete

## Next Steps

- **Seed data:** Learn how to use external datasets in the [seeding tutorial](seeding.md)
- **Execution modes:** Learn more about local and NeMo Services execution in [Execution Modes](../execution-modes.md)
- **Column types:** Explore all available column types in the [library documentation](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/concepts/columns)
- **Advanced features:** Learn about [processors](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/concepts/processors) and [validation](https://docs.nvidia.com/nemo/datadesigner/v0.6.1/concepts/validators)
