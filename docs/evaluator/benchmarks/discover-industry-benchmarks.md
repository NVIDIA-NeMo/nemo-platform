### Discover Industry Benchmarks

Discover industry benchmarks available to use for your evaluation job within the `system` workspace. List all industry benchmarks or filter by label category.

!!! note
    The `system` workspace is a reserved workspace for {{platform_name}} that contains ready-to-use benchmarks representing industry benchmarks with published datasets and metrics.

!!! note
    **Initialization:** This example uses `NeMoPlatform()` with no arguments so the SDK reads your active CLI context (set by `nemo auth login`). The `workspace="system"` is passed per-call to access the reserved system workspace. For the standard local initialization pattern, see [CLI and SDK initialization](../../get-started/setup.md#setup-init).

```python
from nemo_platform import NeMoPlatform

client = NeMoPlatform()

benchmarks = client.evaluation.benchmarks.list(workspace="system")

print(f"{benchmarks.pagination.total_results} benchmarks")
for benchmark in benchmarks:
    print(f"{benchmark.name}: {benchmark.description}")

# List benchmarks with pagination:
benchmarks = client.evaluation.benchmarks.list(
    workspace="system", page=2, page_size=100
)
for benchmark in benchmarks:
    print(f"{benchmark.name}: {benchmark.description}")

# Filter by evaluation category label
filtered_benchmarks = client.evaluation.benchmarks.list(
    workspace="system",
    extra_query={"filter[labels.eval_category]": "advanced_reasoning"},
)
print(filtered_benchmarks)
```

| Category Label | Description |
|----------------|-------------|
| `agentic` | Evaluate the performance of agent-based or multi-step reasoning models, especially in scenarios requiring planning, tool use, and iterative reasoning. |
| `advanced_reasoning` | Evaluate reasoning capabilities of large language models through complex tasks. |
| `code` | Evaluate code generation capabilities using functional correctness benchmarks that test synthesis of working programs. |
| `content_safety` | Evaluate model safety risks including vulnerability to generate harmful, biased, or misleading content. |
| `instruction_following` | Evaluate the ability to follow explicit formatting and structural instructions |
| `language_understanding` | Evaluate knowledge and reasoning across diverse subjects in different languages. |
| `math` | Evaluate mathematical reasoning abilities. |
| `question_answering` | Evaluate the ability to generate answers to questions. |
| `rag` | Evaluate the quality of RAG pipelines by measuring both retrieval and answer generation performance. |
| `retrieval` | Evaluate the quality of document retriever pipelines. |
