<a id="eval-benchmarks-manage-benchmarks"></a>
# Manage Benchmarks

List, retrieve, and delete evaluation benchmarks using the {{platform_name}} Python SDK.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)
```

## List Benchmarks

List all available evaluation benchmarks in a workspace, including both industry benchmarks and custom user-defined benchmarks.

### Basic Usage

```python
# List all benchmarks in the current workspace
benchmarks = client.evaluation.benchmarks.list()
for benchmark in benchmarks:
    print(f"{benchmark.name}: {benchmark.description}")
```

### Pagination

Control the number of results returned per page and navigate through multiple pages of results.

```python
# Get the first page with 50 benchmarks per page
benchmarks = client.evaluation.benchmarks.list(page=1, page_size=50)

# Iterate through all pages
for benchmark in benchmarks:
    print(f"{benchmark.name}: {benchmark.description}")

# Get the second page
benchmarks_page_2 = client.evaluation.benchmarks.list(page=2, page_size=50)
```

### Sorting

Sort benchmarks by different fields in ascending or descending order. Use `-` prefix for descending order.

```python
# Sort by name (ascending)
benchmarks_by_name = client.evaluation.benchmarks.list(sort="name")

# Sort by creation date (most recent first)
benchmarks_recent = client.evaluation.benchmarks.list(sort="-created_at")

# Sort by update date (oldest first)
benchmarks_oldest_updated = client.evaluation.benchmarks.list(sort="updated_at")
```

Available sort fields:
- `name` / `-name`: Sort by benchmark name
- `created_at` / `-created_at`: Sort by creation timestamp
- `updated_at` / `-updated_at`: Sort by last update timestamp

### Extended Response

Use `extended_response=True` to retrieve detailed benchmark information including datasets and metrics configuration.

```python
# Get benchmarks with full details
benchmarks = client.evaluation.benchmarks.list(extended_response=True)
```

### Filter by Label

You can add labels to custom benchmarks when creating them, that can then be used to filter on.

```python
benchmarks = client.evaluation.benchmarks.list(
    extra_query={"filter[labels.my-label]": "my-label-value"}
)
```

## Retrieve a Specific Benchmark

Get detailed information about a specific benchmark by its name within the workspace set for your client.

```python
# Retrieve a benchmark by name
benchmark = client.evaluation.benchmarks.retrieve(name="my-custom-benchmark")
```

### Retrieve with Extended Response

Use `extended_response=True` to get complete benchmark details including datasets and metrics.

```python
# Retrieve benchmark with full configuration
benchmark = client.evaluation.benchmarks.retrieve(
    name="my-custom-benchmark", extended_response=True
)
```

## Filter

Filter benchmarks using the `filter` parameter. Filterable fields are `name`, `description`, `project`, `created_at`, and `updated_at`. Individual labels can be filtered via `extra_query` with bracket notation (e.g. `filter[labels.eval_category]`; see above).
Supports operators `$eq`, `$like`, `$lt`, `$lte`, `$gt`, `$gte`, `$in`, `$nin`
and logical operators `$and`, `$or`, `$not`.

```python
# Filter by name (substring match)
benchmarks = client.evaluation.benchmarks.list(filter={"name": {"$like": "mmlu"}})

# Combine multiple conditions
benchmarks = client.evaluation.benchmarks.list(
    filter={
        "$and": [{"name": {"$like": "mmlu"}}, {"description": {"$like": "reasoning"}}]
    }
)

# Filter by date range
benchmarks = client.evaluation.benchmarks.list(
    filter={
        "created_at": {"$gte": "2025-01-01T00:00:00", "$lte": "2025-06-30T23:59:59"}
    }
)
```

## Delete a Benchmark

Delete a custom evaluation benchmark. Industry benchmarks in the `system` workspace cannot be deleted.

!!! warning
    Deleting a benchmark is permanent and cannot be undone. Ensure the benchmark is not being used by any active evaluations before deletion.

```python
client.evaluation.benchmarks.delete(name="my-custom-benchmark")
```


## Related Topics

- [Custom Benchmarks](custom.md) - Create custom benchmarks
- [Benchmark Job Management](job-management.md) - Manage benchmark evaluation jobs
- [Benchmark Results](results.md) - View and download benchmark evaluation results
