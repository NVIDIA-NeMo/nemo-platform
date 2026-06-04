<a id="fine-tune-format-training-dataset"></a>
# Format Training Dataset

Learn how to format a training dataset to work with the model type you want to train, such as a **chat** or **completion** model.

- **Chat Model** — Requires data that adheres to the `messages` schema.
- **Completion Model** — Requires data that adheres to the `prompt-completion` schema.

Customizer expects _all_ datasets to use JSONL format, where each line in the dataset is a training example serialized in JSON.

## Prerequisites

--8<-- "_snippets/tutorials/prereqs.md"

--8<-- "_snippets/customizer-prereqs.md"

<a id="dataset-best-practices"></a>
## Dataset Best Practices

Before formatting your dataset, follow these principles to ensure high-quality training:

!!! tip
    **Quality Principles:**

    - **Quality > Quantity:** 100 high-quality examples beat 1,000 poor ones
    - **Diversity:** Cover different scenarios, edge cases, and variations
    - **Consistency:** Maintain uniform format, tone, and style across examples
    - **Balance:** Include both common and rare cases relevant to your use case
    - **Validation split:** Reserve 10-20% for validation to detect overfitting

    **Recommended dataset sizes:**

    - **Minimum:** 50-100 examples for simple tasks
    - **Typical:** 500-2,000 examples for most use cases
    - **Large scale:** 10,000+ for complex domains with high variation

### Data Quality Checklist

Before uploading your dataset, verify:

✅ **Format:** All entries are valid JSON on a single line (JSONL) 
✅ **Schema:** Required fields present (`messages`, `prompt`/`completion`, or custom columns) 
✅ **Encoding:** UTF-8 encoding (not UTF-16 or other encodings) 
✅ **Completeness:** No empty or null values in required fields 
✅ **Length:** Examples fit within model's context window (typically 2048-8192 tokens) 
✅ **Split:** Training and validation sets are separate and representative

### Common Dataset Issues

**Overfitting symptoms:**
- Training loss → 0 but validation loss stays high or increases
- Model memorizes training examples verbatim
- Poor generalization to new inputs

**Solutions:**
- Increase dataset size and diversity
- Reduce training epochs (try 1-3 instead of 5+)
- Add more validation data
- Use regularization (dropout, lower learning rate)

**Underfitting symptoms:**
- Both training and validation loss remain high
- Model output quality is poor even on training examples
- Loss plateaus early in training

**Solutions:**
- Increase training epochs (try 5-10 instead of 3)
- Increase model size if using small models
- Check data quality and consistency
- Adjust learning rate (try 5e-5 to 1e-4)

## Chat Models

Chat and instruction models require additional structure in their data to capture concepts such as multi-turn conversations. We support the [OpenAI messages](https://platform.openai.com/docs/guides/text?api-mode=chat) format.

### Format a Conversation Dataset

Train a chat model to optimize for generating responses using multiple messages as context.

#### Basic Schema

A conversational dataset contains a sequence of `messages` that represent interactions between users and assistants. Each message has:

- A `role` field to categorize the message text. Options include `system`, `user`, and `assistant`.
- A `content` field for the actual body of information communicated by that role.

!!! tip
    For best training results, the `assistant` role should be the last message in each training example.

Example entry formatted for JSONL dataset file:

--8<-- "_snippets/output/chat-basic-format-example.jsonl"

??? "Expanded JSON example"

    For illustrative purposes only, we show an example entry as multi-line JSON.

    --8<-- "_snippets/output/chat-expanded-format-example.json"

<a id="ft-tut-format-dataset-reasoning-considerations"></a>
### Reasoning Considerations

Some models (such as [Llama Nemotron](../models/llama-nemotron.md)) support a **detailed thinking** mode, which you can toggle in the system message. This setting controls whether the model is encouraged to show step-by-step reasoning in its responses.

- **Training data without reasoning:** Use `detailed thinking off` in the system message.
- **Training data with reasoning:** Use `detailed thinking on` in the system message.

!!! note
    If you have an existing system message that must be preserved, prepend `detailed thinking on` or `detailed thinking off` to the beginning of your system message.

    For example, if your original system message is `You are a helpful assistant.`, you should use `detailed thinking on\nYou are a helpful assistant.` or `detailed thinking off\nYou are a helpful assistant.`


=== "Detailed Thinking Off"

    --8<-- "_snippets/output/chat-thinking-off-example.jsonl"

=== "Detailed Thinking On"

    --8<-- "_snippets/output/chat-thinking-on-example.jsonl"

You can adjust the system message for each training example to match the style of your data and the behavior you want the model to learn.

#### Schema with Tool Calling

Tool calling (also known as function calling) allows the model to directly interact with external systems based on user inputs. By integrating the model with external applications and APIs, you can significantly expand its capabilities to include:

- Data retrieval from databases or services
- Execution of specific actions in connected systems
- Performance of computation tasks
- Implementation of complex business logic

##### Inline Tools

To train a model with tool calling capabilities, use the conversational dataset format with additional fields. Beyond the standard `messages` structure, you'll need to define the list of `tools` the model can access along with their function parameters. Within the messages, include `tool_calls` when you want the model to invoke a tool with specific arguments.

Every sample must be a single line as in this example below.

--8<-- "_snippets/output/chat-tool-calling-basic-example.jsonl"

??? "Expanded JSON example"

    For illustrative purposes only, we show an example entry as multi-line JSON.

    --8<-- "_snippets/output/chat-tool-calling-expanded-example.json"

##### Shared Tools

When your dataset uses the same set of tools across all examples, you can streamline your configuration by omitting the `tools` field from individual dataset entries. Instead, specify these tools once in the `dataset_parameters` section during job creation.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Create a customization job with shared tools
job = client.customization.jobs.create(
    name="my-tool-calling-job",
    workspace="default",
    spec={
        "model": "default/llama-3-2-1b",
        "dataset": "fileset://default/my-tool-dataset",
        "dataset_parameters": {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "fibonacci",
                        "description": "Calculates the nth Fibonacci number.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "n": {
                                    "description": "The position of the Fibonacci number.",
                                    "type": "integer",
                                }
                            },
                        },
                    },
                }
            ]
        },
        "training": {
            "type": "sft",
            "peft": {"type": "lora", "rank": 8, "alpha": 32},
            "epochs": 10,
            "batch_size": 16,
            "learning_rate": 1e-4,
        },
    },
)

print(f"Created job: {job.name}")
```

### Find Chat Models

You can retrieve a Model Entity to check if it's a chat model by examining the `spec.is_chat` field:

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Get a specific model
model = client.models.retrieve(name="llama-3-2-1b", workspace="default")

print(f"Model: {model.name}")
if model.spec:
    print(f"Is Chat Model: {model.spec.is_chat}")
    print(f"Family: {model.spec.family}")
    print(f"Parameters: {model.spec.base_num_parameters:,}")
    print(f"Max Sequence Length: {model.spec.max_sequence_length}")
```

### Chat with the Model

To run inference with a chat model, you first need to deploy the model, then use the Inference Gateway to send requests.

!!! note
    Before running inference, ensure your model is deployed. See [about](../../run-inference/about.md) for details on creating a ModelDeploymentConfig and ModelDeployment.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Use Inference Gateway with OpenAI-compatible client
oai_client = client.models.get_openai_client(workspace="default")

# Create a chat completion (model format: "workspace/model-entity-name")
response = oai_client.chat.completions.create(
    model="default/llama-3-2-1b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! How are you?"},
    ],
    temperature=0.5,
    top_p=1,
    max_tokens=1024,
)

print(f"Response: {response.choices[0].message.content}")
```

## Next Steps

Now that you know how to format your training datasets, you can proceed with creating customization jobs:

- [Start a LoRA Model Customization Job](./lora-customization-job.ipynb) - For parameter-efficient fine-tuning
- [Start a Full SFT Customization Job](./sft-customization-job.ipynb) - For full model fine-tuning
- [Start a DPO Customization Job](./dpo-customization-job.ipynb) - For preference-based alignment

---

## Completion Models

Train a model using the completion dataset format for tasks like text summarization, information extraction, question answering, text classification, reasoning, or story writing.

### Format a Prompt-Completion Dataset

Prompt completion datasets have a simple schema. Each datum has:

- A `prompt` field for the body of information provided by the user.
- A `completion` field for output of the model.

--8<-- "_snippets/output/completion-format-example.jsonl"

### Prompt the Model

To run inference with a completion model, use the Inference Gateway to send requests to the `/completions` endpoint.

!!! note
    Before running inference, ensure your model is deployed. See [about](../../run-inference/about.md) for details on creating a ModelDeploymentConfig and ModelDeployment.

```python
import os
from nemo_platform import NeMoPlatform

client = NeMoPlatform(
    base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
    workspace="default",
)

# Use Inference Gateway with OpenAI-compatible client
oai_client = client.models.get_openai_client(workspace="default")

# Create a completion (model format: "workspace/model-entity-name")
response = oai_client.completions.create(
    model="default/llama-3-2-1b",
    prompt="Once upon a time",
    temperature=0.5,
    top_p=1,
    max_tokens=1024,
)

print(f"Response: {response.choices[0].text}")
```
