<a id="eval-benchmarks-industry"></a>
# Industry Benchmarks

## Evaluate with Published Datasets

{{platform_name}} provides a streamlined API to evaluate large language models with publicly available datasets, offering over 130 industry benchmarks to run with evaluation jobs.

Benchmarks provide standardized methods for comparing model performance across different capabilities. These benchmarks are widely used in the research community and provide reliable, reproducible metrics for model assessment.

Refer to the [Run an LLM Judge Evaluation](../tutorials/run-llm-judge-evaluation.md) tutorial for details on using evaluator jobs and result handling.

- **Standard Datasets**: Most benchmarks include predefined datasets widely used in research.
- **Reproducible Metrics**: Use established methodologies to calculate metrics.
- **Community Standards**: You can compare results across different models and research groups.

--8<-- "evaluator/benchmarks/discover-industry-benchmarks.md"

### Choosing a Benchmark Variant

Many benchmarks offer multiple variants optimized for different model types:

| Variant | Endpoint | Description |
|---------|----------|-------------|
| `-instruct` | `/v1/chat/completions` | Zero-shot evaluation for instruction-tuned models |
| Base (no suffix) | `/v1/completions` | Few-shot evaluation for base models (requires `tokenizer` param) |
| `-nemo` | `/v1/chat/completions` | Optimized prompts for NVIDIA NeMo models; often no judge required |
| `-cot` | `/v1/chat/completions` | Chain-of-thought prompting for improved reasoning accuracy |

### Common Parameters

| Parameter | Description |
|-----------|-------------|
| `parallelism` | Number of concurrent inference requests. Higher values increase throughput but can hit rate limits. |
| `limit_samples` | Evaluate only the first N samples. Useful for testing before running full evaluations. |
| `hf_token` | Reference to a secret containing your Hugging Face token for accessing gated datasets. |
| `tokenizer` | Hugging Face tokenizer ID, required for completions-based benchmarks. |

!!! tip
    The `model` field in all benchmark examples below accepts either an inline model definition or a model reference string (for example, `"my-workspace/my-model"`). Refer to [Model Configuration](../metrics/model-configuration.md) for details.

## Advanced Reasoning

Evaluate reasoning capabilities of large language models through complex tasks with datasets like GPQA, BIG-Bench Hard (BBH), or Multistep Soft Reasoning (MuSR).

* Label: `eval_category.advanced_reasoning`

### Available Benchmarks

To get the latest benchmarks available for your system, [filter with the `eval_category.advanced_reasoning` label](#discover-industry-benchmarks).

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/gpqa-diamond` | [GPQA](https://arxiv.org/abs/2311.12022) Diamond subset—198 graduate-level science questions | `hf_token` |
| `system/gpqa-extended` | GPQA Extended subset—546 questions in biology, physics, chemistry | `hf_token` |
| `system/gpqa-main` | GPQA Main subset—448 questions | `hf_token` |
| `system/gpqa-diamond-nemo` | GPQA Diamond with NeMo alignment template | `hf_token` |
| `system/gpqa-diamond-cot` | GPQA Diamond with chain-of-thought prompting | `hf_token` |
| `system/gpqa` | GPQA few-shot evaluation ¹ | `hf_token`, `tokenizer` |
| `system/bbh-instruct` | [BIG-Bench Hard](https://github.com/google/BIG-bench)—23 challenging reasoning tasks | `hf_token` |
| `system/bbh` | BIG-Bench Hard ¹ | `hf_token`, `tokenizer` |
| `system/musr` | [MuSR](https://arxiv.org/abs/2310.16049)—multistep reasoning through narrative problems ¹ | `hf_token`, `tokenizer` |

**¹** Completions-only: Requires `/v1/completions` endpoint and `tokenizer` parameter.

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)
```

=== "GPQA Diamond"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA Diamond evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa-diamond",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GPQA Extended"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA Extended evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa-extended",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GPQA Main"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA Main evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa-main",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GPQA Diamond (NeMo)"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA Diamond evaluation with NeMo template",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa-diamond-nemo",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GPQA Diamond CoT"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA Diamond chain-of-thought evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa-diamond-cot",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GPQA (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GPQA few-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gpqa",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

=== "BBH Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="BIG-Bench Hard evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/bbh-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "BBH (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="BIG-Bench Hard evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/bbh",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

=== "MuSR (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="Multistep Soft Reasoning evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/musr",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

!!! note

    --8<-- "evaluator/benchmarks/hf-secret.md"

### Results

All advanced reasoning benchmarks produce an **accuracy** score (0.0–1.0) measuring the proportion of correct answers:

- **GPQA**: Multiple-choice accuracy (random baseline = 25%)
- **BBH**: Exact match accuracy across 23 reasoning tasks
- **MuSR**: Accuracy on multistep reasoning narratives

```python
# Get results after the job completes
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name,
)

# Print accuracy
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

## Instruction Following

Evaluate a model's ability to follow explicit formatting and structural instructions such as "include keyword x" or "use format y."

* Label: `instruction_following`

### Available Benchmarks

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/ifeval` | [IFEval](https://arxiv.org/abs/2311.07911)—500 prompts testing adherence to verifiable instructions | `hf_token` |

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)

job = client.evaluation.benchmark_jobs.create(
    description="IFEval instruction following evaluation",
    spec=SystemBenchmarkOnlineJobParam(
        benchmark="system/ifeval",
        model={
            "url": "<your-nim-endpoint>/v1",
            "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
        },
        params=RunConfig(parallelism=16),
        benchmark_params={"hf_token": "hf_token"},
    ),
)
```

### Results

IFEval produces multiple accuracy scores measuring instruction compliance:

- **Prompt-level accuracy**: Percentage of prompts where all instructions were followed
- **Instruction-level accuracy**: Percentage of individual instructions followed across all prompts

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name
)
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

## Language Understanding

Evaluate knowledge and reasoning across diverse subjects using MMLU (Massive Multitask Language Understanding) benchmarks covering 57 subjects across STEM, humanities, social sciences, and more.

* Label: `language_understanding`

### Available Benchmarks

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/mmlu` | [MMLU](https://arxiv.org/abs/2009.03300)—57 subjects, few-shot evaluation ¹ | `hf_token`, `tokenizer` |
| `system/mmlu-instruct` | MMLU zero-shot with single-letter response format | `hf_token` |
| `system/mmlu-pro` | [MMLU-Pro](https://arxiv.org/abs/2406.01574)—10 answer choices, more rigorous ¹ | `hf_token`, `tokenizer` |
| `system/mmlu-pro-instruct` | MMLU-Pro zero-shot with chat template | `hf_token` |
| `system/mmlu-redux` | [MMLU-Redux](https://arxiv.org/abs/2406.04127)—3,000 re-annotated questions ¹ | `hf_token`, `tokenizer` |
| `system/mmlu-redux-instruct` | MMLU-Redux zero-shot with chat template | `hf_token` |
| `system/wikilingua` | [WikiLingua](https://arxiv.org/abs/2010.03093)—cross-lingual summarization | `hf_token` |
| `system/mmlu-{lang}` | [Global-MMLU](https://huggingface.co/datasets/CohereForAI/Global-MMLU) in 30+ languages ² | `hf_token` |

**¹** Completions-only: Requires `/v1/completions` endpoint and `tokenizer` parameter.

**²** Supported languages: `am`, `ar`, `bn`, `cs`, `de`, `el`, `en`, `es`, `fa`, `fil`, `fr`, `ha`, `he`, `hi`, `id`, `ig`, `it`, `ja`, `ko`, `ky`, `lt`, `mg`, `ms`, `ne`, `nl`, `ny`, `pl`, `pt`, `ro`, `ru`, `si`, `sn`, `so`, `sr`, `sv`, `sw`, `te`, `tr`, `uk`, `vi`, `yo`

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)
```

=== "MMLU Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MMLU zero-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "MMLU (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MMLU few-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

=== "MMLU-Pro Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MMLU-Pro zero-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu-pro-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "MMLU-Pro (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MMLU-Pro few-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu-pro",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

=== "MMLU-Redux Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MMLU-Redux zero-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu-redux-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "MMLU Spanish"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="Global-MMLU Spanish evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mmlu-es",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "WikiLingua"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="WikiLingua cross-lingual summarization",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/wikilingua",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

### Results

Language understanding benchmarks produce accuracy scores:

- **MMLU/MMLU-Pro/MMLU-Redux**: Multiple-choice accuracy across subjects (random baseline = 25% for MMLU, 10% for MMLU-Pro)
- **WikiLingua**: ROUGE scores for summarization quality

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name
)
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

## Math & Reasoning

Evaluate mathematical reasoning abilities from grade school arithmetic to competition-level mathematics.

* Label: `math`

### Available Benchmarks

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/gsm8k` | [GSM8K](https://arxiv.org/abs/2110.14168)—1,319 grade school math problems ¹ | `hf_token`, `tokenizer` |
| `system/gsm8k-cot-instruct` | GSM8K with chain-of-thought zero-shot | `hf_token` |
| `system/mgsm` | [MGSM](https://arxiv.org/abs/2210.03057)—multilingual math (10 languages) ¹ | `hf_token`, `tokenizer` |
| `system/mgsm-cot` | MGSM with chain-of-thought prompting | `hf_token` |
| `system/aime-2024` | [AIME 2024](https://artofproblemsolving.com/wiki/index.php/2024_AIME_I)—competition math ² | `judge` |
| `system/aime-2025` | AIME 2025—competition math ² | `judge` |
| `system/aime-2024-nemo` | AIME 2024 with NeMo template | — |
| `system/aime-2025-nemo` | AIME 2025 with NeMo template | — |
| `system/math-test-500` | [MATH](https://arxiv.org/abs/2103.03874) test set (500 problems) ² | `judge` |
| `system/math-test-500-nemo` | MATH test with NeMo template | — |
| `system/aa-aime-2024` | AIME 2024 (Artificial Analysis setup) ² | `judge` |
| `system/aa-math-test-500` | MATH test (Artificial Analysis setup) ² | `judge` |

**¹** Completions-only: Requires `/v1/completions` endpoint and `tokenizer` parameter.

**²** Judge required: Requires a judge model to evaluate free-form math responses.

!!! info
    For math benchmarks requiring a judge, use a model with strong instruction-following capabilities (70B+ parameters recommended). Smaller models may produce malformed judge outputs.

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)
```

=== "GSM8K CoT Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GSM8K chain-of-thought evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gsm8k-cot-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "GSM8K (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="GSM8K few-shot evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/gsm8k",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "tokenizer": "<your-model-tokenizer>",
            },
        ),
    )
    ```

=== "MGSM CoT"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MGSM multilingual math evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mgsm-cot",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={"hf_token": "hf_token"},
        ),
    )
    ```

=== "AIME 2025 (NeMo)"

    No judge required with NeMo template.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="AIME 2025 competition math",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/aime-2025-nemo",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "AIME 2025 (Judge)"

    Requires a judge model.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="AIME 2025 competition math with judge",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/aime-2025",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "judge": {
                    "model": {
                        "url": "<your-nim-endpoint>/v1",
                        "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
                    }
                }
            },
        ),
    )
    ```

=== "MATH Test 500 (NeMo)"

    No judge required with NeMo template.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MATH test set evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/math-test-500-nemo",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

### Results

Math benchmarks produce accuracy scores:

- **GSM8K/MGSM**: Exact match accuracy on final numerical answers
- **AIME/MATH**: Correctness as judged by the judge model (or exact match for NeMo variants)

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name
)
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

<a id="eval-content-safety-benchmark"></a>
## Content Safety

Evaluate model safety risks including vulnerability to generate harmful, biased, or misleading content.

* Label: `content_safety`

### Available Benchmarks

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/aegis-v2` | [AEGIS 2.0](https://aclanthology.org/2025.naacl-long.306/)—12 hazard categories using Nemotron Safety Guard | `hf_token`, `judge` |
| `system/wildguard` | [WildGuard](https://arxiv.org/abs/2406.18495)—privacy, misinformation, harmful language | `hf_token`, `judge` |

!!! info
    Safety benchmarks require specific judge models deployed with a `/v1/completions` endpoint (not chat/completions):

    | Benchmark | Required Judge Model | Model ID |
    |-----------|---------------------|----------|
    | `system/aegis-v2` | [Llama Nemotron Safety Guard V2](https://huggingface.co/nvidia/llama-3.1-nemoguard-8b-content-safety) | `nvidia/llama-3.1-nemoguard-8b-content-safety` |
    | `system/wildguard` | [WildGuard](https://huggingface.co/allenai/wildguard) | `allenai/wildguard` |


The benchmarks can take up to 1-3 hours.

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)
```

=== "AEGIS-v2"

    Requires Llama Nemotron Safety Guard V2 judge.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="AEGIS-v2 content safety evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/aegis-v2",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "judge": {
                    "model": {
                        "url": "<your-safety-guard-endpoint>/v1/completions",
                        "name": "nvidia/llama-3.1-nemoguard-8b-content-safety",
                    }
                },
            },
        ),
    )
    ```

=== "WildGuard"

    Requires WildGuard judge.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="WildGuard content safety evaluation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/wildguard",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
            benchmark_params={
                "hf_token": "hf_token",
                "judge": {
                    "model": {
                        "url": "<your-wildguard-endpoint>/v1/completions",
                        "name": "allenai/wildguard",
                    }
                },
            },
        ),
    )
    ```

### Results

Safety benchmarks produce category-level safety rates:

- **AEGIS-v2**: Safe/unsafe classification across 12 hazard categories (violence, hate, sexual content, and so on)
- **WildGuard**: Safe/unsafe classification for privacy, misinformation, harmful language, malicious use

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name
)
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

### Troubleshooting Content Safety Benchmarks

Refer to [Evaluator Troubleshooting](../../troubleshooting/evaluator.md) for general troubleshooting steps for failed evaluation jobs.

<details>
<summary>This section covers common issues for the safety harness.</summary>

#### Hugging Face Error

Evaluations with safety harness requires Hugging Face access to the respective dataset and model tokenizer. If your job fails with the following errors, visit [https://huggingface.co/](https://huggingface.co/) and log in to request access to the dataset or model.

```text
datasets.exceptions.DatasetNotFoundError: Dataset 'allenai/wildguardmix' is a gated dataset on the Hub. Visit the dataset page at https://huggingface.co/datasets/allenai/wildguardmix to ask for access.
```

```text
GatedRepoError: 403 Client Error.

Cannot access gated repo for url https://huggingface.co/<model>/resolve/main/tokenizer_config.json.
Your request to access model <model> is awaiting a review from the repo authors.
```

#### Incompatible Judge Model

Using an unsupported judge model results in a job error. The `aegis-v2` evaluation requires Llama Nemotron Safety Guard V2 judge and `wildguard` evaluation requires `allenai/wildguard` judge. `KeyError` is an example error for the wrong judge model like the following error.

```text
Metrics calculated


 Evaluation Metrics
┏━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┓
┃ Safety Category ┃ Average Count ┃
┡━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ ERROR │ 5.0 │
└─────────────────┴───────────────┘

...

Subprocess finished with return code: 0
{'ERROR': 5.0}
Traceback (most recent call last):
...
"/usr/local/lib/python3.10/site-packages/core_evals/safety_eval/__init__.py", line 14, in parse_output
 return parse_output(output_dir)
 File "/usr/local/lib/python3.10/site-packages/core_evals/safety_eval/output.py", line 16, in parse_output
 safety_rate = data['safe'] / sum(data.values())
KeyError: 'safe'
```

#### Unexpected Reasoning Traces

Safety evaluations do not support reasoning traces and may result in the job error below.

```text
ERROR There are at least 2 MUT (model under test) responses that start with <think>. Reasoning traces should not be evaluated. Exiting.
```

If the model or judge outputs reasoning traces like `<think>reasoning context</think>answer`, configure the job to only include the the final answer after the reasoning token (e.g. `</think>`) with `reasoning.end_token`. Consider specifying `inference.max_tokens` to a reasonable limit for the model's chain of thought to conclude with the expected reasoning end token in order for the reasoning context to be properly omitted for evaluation.

Additionally, if you are encountering this error, it could be caused by the model exceeding its token limit resulting in the full response being consumed by the model thinking. These results can be dropped by setting the `reasoning.include_if_not_finished` parameter.

```python
from nemo_platform.types.evaluation import (
    RunConfig,
    InferenceParams,
    ReasoningParams,
)

params = RunConfig(
    inference=InferenceParams(max_tokens=1024),
    reasoning=ReasoningParams(
        end_token="</think>",
        include_if_not_finished=False,
    ),
)
```

</details>

## Code

Evaluate code generation capabilities using functional correctness benchmarks that test synthesis of working programs.

* Label: `code`

### Available Benchmarks

| Benchmark | Description | Required Params |
|-----------|-------------|-----------------|
| `system/humaneval` | [HumanEval](https://arxiv.org/abs/2107.03374)—164 Python problems ¹ | — |
| `system/humaneval-instruct` | HumanEval for instruction-tuned models | — |
| `system/humanevalplus` | [HumanEval+](https://arxiv.org/abs/2305.01210)—80x more test cases ¹ | — |
| `system/mbpp` | [MBPP](https://arxiv.org/abs/2108.07732)—Python programming problems | — |
| `system/mbppplus` | [MBPP+](https://arxiv.org/abs/2305.01210)—35x more test cases | — |
| `system/mbppplus-nemo` | MBPP+ with NeMo template | — |
| `system/multiple-{lang}` | [MultiPL-E](https://arxiv.org/abs/2208.08227)—HumanEval in 20+ languages ¹ | — |

**¹** Completions-only: Requires `/v1/completions` endpoint.

**MultiPL-E languages**: `clj` (Clojure), `cpp` (C++), `cs` (C#), `d`, `elixir`, `go`, `hs` (Haskell), `java`, `jl` (Julia), `js` (JavaScript), `lua`, `ml` (OCaml), `php`, `pl` (Perl), `r`, `rb` (Ruby), `rkt` (Racket), `rs` (Rust), `scala`, `sh` (Bash), `swift`

The benchmarks can take up to 1–5 hours.

### Examples

```python
import os
from nemo_platform import NeMoPlatform
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="my-workspace",  # Replace with your workspace or use "default"
)
```

=== "HumanEval Instruct"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="HumanEval code generation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/humaneval-instruct",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "HumanEval (Completions)"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="HumanEval code generation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/humaneval",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "HumanEval+ (Completions)"

    Extended test suite with 80x more test cases.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="HumanEval+ code generation",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/humanevalplus",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "MBPP+ (NeMo)"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MBPP+ Python programming",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mbppplus-nemo",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "MBPP+"

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MBPP+ Python programming",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/mbppplus",
            model={
                "url": "<your-nim-endpoint>/v1",
                "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "MultiPL-E JavaScript"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MultiPL-E JavaScript",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/multiple-js",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

=== "MultiPL-E Rust"

    Requires a `/v1/completions` endpoint.

    ```python
    job = client.evaluation.benchmark_jobs.create(
        description="MultiPL-E Rust",
        spec=SystemBenchmarkOnlineJobParam(
            benchmark="system/multiple-rs",
            model={
                "url": "<your-nim-endpoint>/v1/completions",
                "name": "<your-base-model>",
            },
            params=RunConfig(parallelism=16),
        ),
    )
    ```

### Results

Code benchmarks produce pass@k metrics measuring functional correctness:

- **pass@1**: Percentage of problems solved with one attempt
- **pass@10**: Percentage of problems solved within 10 attempts (when `n_samples` > 1)

```python
aggregate = client.evaluation.benchmark_jobs.results.aggregate_scores.download(
    job=job.name
)
for score in aggregate.scores:
    print(f"{score.name}: {score.mean:.1%}")
```

For detailed results analysis, refer to [eval-benchmark-results](results.md).

!!! tip
    **Want to experiment first?** You can try these benchmarks using the [open-source NeMo Evaluator SDK](https://github.com/NVIDIA-NeMo/evaluator) before deploying the platform. The SDK provides a lightweight way to test evaluation workflows locally.

## Run Benchmark Job

Create a workspace if you have not already.

```python
workspace = "my-workspace"

client.workspaces.create(name=workspace)
```

Create an evaluation job with a benchmark that satisfy the required and optional parameters.

!!! note
    For benchmarks that require a Hugging Face token or other API keys for external services, create the secret to be referenced by the job.

    --8<-- "evaluator/benchmarks/hf-secret.md"

```python
from nemo_platform.types.evaluation import (
    SystemBenchmarkOnlineJobParam,
    RunConfig,
)

job = client.evaluation.benchmark_jobs.create(
    description="Example running system benchmark to evaluate my model's advanced reasoning capabilities.",
    spec=SystemBenchmarkOnlineJobParam(
        benchmark="system/gpqa-diamond-cot",
        model={
            "url": "<your-nim-endpoint>/v1",
            "name": "nvidia/llama-3.3-nemotron-super-49b-v1",
        },
        params=RunConfig(parallelism=16),
        benchmark_params={"hf_token": "hf_token"},
    ),
)
```

## Job Management

After creating a job, navigate to [Benchmark Job Management](job-management.md) to oversee its execution and monitor progress.
