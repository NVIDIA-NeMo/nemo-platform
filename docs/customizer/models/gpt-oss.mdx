<a id="model-catalog-gpt-oss"></a>
# GPT-OSS Models

This page provides detailed technical specifications for the OpenAI GPT-OSS model family supported by {{ncm_short_name}}. For supported features and capabilities, refer to [Tested Models](index.md).

## Before You Start

These models require a HuggingFace token to download. Create a secret with your HuggingFace API key, then create a FileSet and Model Entity referencing the model. See [index](../manage-model-entities/index.md) for setup instructions.

---

## GPT-OSS 20B

| Property | Value |
|----------|-------|
| Creator | OpenAI |
| Architecture | Mixture of Experts (MoE) Transformer |
| Description | GPT-OSS 20B provides lower latency for local or specialized use cases, featuring full chain-of-thought reasoning and agentic capabilities. |
| Max I/O Tokens | Not specified |
| Parameters | 21B parameters (3.6B active parameters) |
| Training Data | Trained on harmony response format |
| Memory Requirements | Runs within 32GB of memory with BFloat16 quantization |
| Default Name | openai/gpt-oss-20b |
| HuggingFace | [openai/gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) |

### Training Options (20B)

- **LoRA**: 4x 80GB GPU, tensor parallel size 1, expert parallel size 4, pipeline parallel size 1
- **Full SFT**: 8x 80GB GPU, tensor parallel size 1, expert parallel size 8, pipeline parallel size 1
- Sequence Packing: Not supported

Default training max sequence length: 4096.

### Deployment Configuration

- **LoRA**:
 - NIM Image: `nvcr.io/nim/openai/gpt-oss-20b:1.6.1-variant`
 - GPU Count: 2x 80GB
 - Additional Environment Variables:
 - `NIM_DISABLE_MODEL_DOWNLOAD`: `1`
 - `NIM_WORKSPACE`: `/model-store`
- **Full SFT**:
 - NIM Image: `nvcr.io/nim/nvidia/llm-nim:1.15.5`
 - GPU Count: 2x 80GB
 - Additional Environment Variables:
 - `NIM_MODEL_PROFILE`: `vllm`

## Usage Recommendations

### Reasoning Levels

Both GPT-OSS models support configurable reasoning levels that you can set in system prompts:

- **Low**: Fast responses for general dialogue
- **Medium**: Balanced speed and detail
- **High**: Deep and detailed analysis

Example: Set reasoning level using "Reasoning: high" in the system prompt.

### MoE Model Parallelization

GPT-OSS models use a Mixture of Experts (MoE) architecture and benefit from specialized parallelization across expert layers for optimal performance. 

!!! note
    **MoE Parallelism Constraints**

    MoE models only support expert parallelism for distributing experts across GPUs. When `expert_parallel_size > 1`, `tensor_parallel_size` must be set to 1. Additionally, `expert_parallel_size` must evenly divide the number of GPUs. These constraints apply to training parallelism only and NIM deployment may use different GPU counts optimized for inference.

### Model Selection Guidelines

- **GPT-OSS 20B**: Ideal for lower latency requirements, local deployment, specialized use cases, and consumer hardware (with Ollama support)
- **GPT-OSS 120B**: Best for production environments, complex reasoning tasks, and scenarios requiring full capability within single-GPU constraints

### Important Usage Note

Both models use the harmony response format and require this format for proper functionality.

!!! note
    Sequence packing is not supported for GPT-OSS models in {{ncm_short_name}}.
