
<a id="ft-tut-private-reg"></a>
# Import and Fine-Tune Private HuggingFace Models

Use this tutorial to learn how to import a private HuggingFace model into NeMo Customizer, fine-tune it with LoRA, and deploy it for inference.

## Prerequisites

--8<-- "_snippets/tutorials/prereqs.md"

--8<-- "_snippets/customizer-prereqs.md"

### Tutorial-Specific Prerequisites

- Access to Data Store and Deployment Manager service
- `hf` cli installed on a machine with internet access [(installation instructions)](https://huggingface.co/docs/huggingface_hub/main/en/guides/cli).
- A HuggingFace model with a **compatible architecture**. Not all HuggingFace models are compatible with NeMo Customizer. This tutorial uses `gemma-2-2b-it` as an example, but success depends on architectural compatibility.
- A HuggingFace API token and proper authentication setup.
- Sufficient storage space for the model files (typically 5-50GB depending on model size)
- At least 8GB GPU memory for smaller models, more for larger models

!!! note
    Verify that all required services are running and accessible before proceeding. You can check service health using the health endpoints documented in each service's API specification.

### Known Issues

!!! warning
    **Conv1D Model Architecture Limitation**: Models that use `Conv1D` layers are not compatible with NeMo Customizer AutoModel LoRA.

    **Error signature**: `AttributeError: 'Conv1D' object has no attribute 'config'`

    **Affected models include:**

    - `microsoft/DialoGPT-*` series
    - `openai-gpt` models
    - Some older `gpt2` variants
    - Other models with Conv1D-based architectures

    **Root cause**: These models use Conv1D layers that lack the linear layers expected by NeMo's LoRA transformation utilities.

    **Solution**: Use modern transformer architectures instead:

    - ✅ **Recommended**: Llama models (3.1, 3.2, 3.3 series)
    - ✅ **Recommended**: Nemotron models
    - ✅ **Recommended**: Phi models
    - ✅ **Alternative**: Gemma models (used in this tutorial)

    For a complete list of tested models, see the [Model Catalog](../models/index.md).

---

## Download Model From HuggingFace Hub

1. Authenticate to HuggingFace using `hf auth login`.
2. Download the model.

    --8<-- "_snippets/input/common.sh"

---

## Create Model in Data Store

Next, create a model repository in the NeMo Data Store and upload the downloaded model files.

### Create Namespace and Model Repository

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash
    # Set environment variables - Update these to match your deployment
    export NAMESPACE="my-org"
    export MODEL_NAME="gemma-2-2b-it"
    export MODEL_VERSION="$(date +%Y%m%d-%H%M%S)" # Unique version for this run
    export NEMO_BASE_URL="http://nemo.test"
    export DATASTORE_URL="http://data-store.test"
    export REPO_ID="${NAMESPACE}/${MODEL_NAME}"
    export DATASET_NAME="${MODEL_NAME}-training-data"

    # Create namespace
    curl -X POST "${DATASTORE_URL}/v1/datastore/namespaces" \
    -H 'Content-Type: application/json' \
    -d '{"namespace": "'${NAMESPACE}'"}'

    # Create model repository in datastore
    curl -X POST "${DATASTORE_URL}/v1/hf/api/repos/create" \
    -H 'Content-Type: application/json' \
    -d '{
    "organization": "'${NAMESPACE}'",
    "name": "'${MODEL_NAME}'",
    "type": "model"
    }'
    ```

### Upload Model Files to Data Store

Upload the downloaded model files to the Data Store repository:

--8<-- "_snippets/input/common.py"

## Create Model Entity in Entity Store

After uploading the model files to the Data Store, create a model entity in the Entity Store to register the model with its metadata and specifications for use in customization jobs.

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash
    # Create model entity in Entity Store
    curl -X POST "${NEMO_BASE_URL}/v1/models" \
    -H 'Content-Type: application/json' \
    -d '{
    "name": "'${MODEL_NAME}'",
    "namespace": "'${NAMESPACE}'",
    "description": "Private '${MODEL_NAME}' model imported for customization",
    "artifact": {
    "files_url": "hf://models/'${REPO_ID}'",
    "backend_engine": "hugging_face",
    "status": "upload_completed"
    },
    "spec": {
    "num_parameters": 200000000,
    "context_size": 1024,
    "is_chat": true,
    "num_virtual_tokens": -1
    },
    "peft": {
    "finetuning_type": "all_weights"
    }
    }' | jq .
    ```

## Deploy the Base Model

Deploy the base model for inference with LoRA adapter support enabled, allowing it to load fine-tuned adapters from customization jobs.

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash
    curl "${NEMO_BASE_URL}/v1/deployment/configs" \
    -X POST \
    -H 'Content-Type: application/json' \
    --data-binary '{
    "model": "'${MODEL_NAME}'",
    "name": "'${MODEL_NAME}'-deployment-config",
    "namespace": "'${NAMESPACE}'",
    "nim_deployment": {
    "additional_envs": {
    "NIM_FT_MODEL": "",
    "NIM_GUIDED_DECODING_BACKEND": "outlines",
    "NIM_JSONL_LOGGING": "0",
    "NIM_MODEL_NAME": "/model-store",
    "NIM_PEFT_REFRESH_INTERVAL": "30",
    "NIM_PEFT_SOURCE": "http://nemo-entity-store:8000",
    "UVICORN_LOG_LEVEL": "DEBUG",
    "VLLM_NVEXT_LOG_LEVEL": "DEBUG"
    },
    "gpu": 1,
    "image_name": "nvcr.io/nim/nvidia/llm-nim",
    "image_tag": "1.13.1",
    "disable_lora_support": false
    }
    }' | jq .


    curl "${NEMO_BASE_URL}/v1/deployment/model-deployments" \
    -X POST \
    -H 'Content-Type: application/json' \
    -d '{
    "name": "'${MODEL_NAME}'-deployment",
    "namespace": "'${NAMESPACE}'",
    "config": "'${NAMESPACE}'/'${MODEL_NAME}'-deployment-config"
    }' | jq .

    ```

## Create Customization Target

Create a customization target that references the uploaded model in the Data Store.

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash

    # Create customization target
    curl -X POST \
    "${NEMO_BASE_URL}/v1/customization/targets" \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{
    "name": "'${MODEL_NAME}'@v'${MODEL_VERSION}'",
    "namespace": "'${NAMESPACE}'",
    "description": "Customization target for '${MODEL_NAME}'",
    "enabled": true,
    "model_uri": "hf://'${NAMESPACE}'/'${MODEL_NAME}'",
    "num_parameters": 200000000,
    "precision": "bf16-mixed"
    }' | jq .
    ```

Wait for the model to be downloaded and ready:

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "CLI"

    ```bash
    # Check target status with comprehensive handling
    while true; do
    RESPONSE=$(curl -s -X GET \
    "${NEMO_BASE_URL}/v1/customization/targets/${NAMESPACE}/${MODEL_NAME}@v${MODEL_VERSION}" \
    -H 'accept: application/json')

    STATUS=$(echo "$RESPONSE" | jq -r '.status')
    echo "Target status: $STATUS"

    if [ "$STATUS" = "ready" ]; then
    echo "Model is ready for customization!"
    break
    elif [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ] || [ "$STATUS" = "unknown" ] || [ "$STATUS" = "delete_failed" ]; then
    echo "Model download failed with status: $STATUS"
    echo "Contact your administrator for assistance."
    break
    elif [ "$STATUS" = "created" ] || [ "$STATUS" = "pending" ] || [ "$STATUS" = "downloading" ]; then
    echo "Model is still being prepared, waiting..."
    elif [ "$STATUS" = "deleted" ] || [ "$STATUS" = "deleting" ]; then
    echo "Model is being deleted (status: $STATUS)"
    echo "This target cannot be used for customization."
    break
    else
    echo "Unknown status: $STATUS"
    fi

    sleep 30
    done

    ```

## Create Customization Configuration

Create a configuration for LoRA fine-tuning:

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash
    # Create customization configuration
    curl -X POST \
    "${NEMO_BASE_URL}/v1/customization/configs" \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{
    "name": "'${MODEL_NAME}'-lora-config@v'${MODEL_VERSION}'",
    "namespace": "'${NAMESPACE}'",
    "target": "'${NAMESPACE}'/'${MODEL_NAME}'@v'${MODEL_VERSION}'",
    "description": "LoRA configuration for '${MODEL_NAME}'",
    "training_options": [
    {
    "training_type": "sft",
    "finetuning_type": "lora",
    "num_gpus": 1,
    "num_nodes": 1,
    "tensor_parallel_size": 1,
    "pipeline_parallel_size": 1,
    "micro_batch_size": 1
    }
    ],
    "training_precision": "bf16-mixed",
    "max_seq_length": 1024,
    "prompt_template": "{prompt} {completion}"
    }' | jq .
    ```

---

## Prepare Training and Validation Datasets

Before starting the customization job, prepare both training and validation datasets. The validation dataset helps track training progress and reduce overfitting.

Create datasets in JSONL format:

```python
import json
# Note: This assumes MODEL_NAME, NAMESPACE, and hf_api are already defined from previous code blocks

# Example training data for Gemma 2 (instruction format)
# Gemma 2 uses standard chat message format
training_data = [
    {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
            {
                "role": "assistant",
                "content": "I'm doing well, thank you for asking! How can I assist you today?",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What's the weather like?"},
            {
                "role": "assistant",
                "content": "I don't have access to current weather data, but I can help you find weather information or discuss weather patterns.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Tell me a joke"},
            {
                "role": "assistant",
                "content": "Why don't scientists trust atoms? Because they make up everything!",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Can you help me with coding?"},
            {
                "role": "assistant",
                "content": "Absolutely! I'd be happy to help you with coding. What programming language or specific problem are you working on?",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What is machine learning?"},
            {
                "role": "assistant",
                "content": "Machine learning is a subset of artificial intelligence that enables computers to learn and make decisions from data without being explicitly programmed.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "How do I write a function in Python?"},
            {
                "role": "assistant",
                "content": "To write a function in Python, use the 'def' keyword followed by the function name and parameters: def my_function(param): return result",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What are the benefits of exercise?"},
            {
                "role": "assistant",
                "content": "Exercise offers numerous benefits including improved cardiovascular health, stronger muscles, better mental health, and increased energy levels.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Explain the solar system"},
            {
                "role": "assistant",
                "content": "The solar system consists of the Sun and all celestial objects that orbit it, including eight planets, moons, asteroids, and comets.",
            },
        ]
    },
]

# Expand training data by repeating examples to create a larger dataset
training_data = training_data * 10  # 80 total examples (8 unique * 10 repetitions)

# Save training data to JSONL file
with open("training_data.jsonl", "w") as f:
    for item in training_data:
        f.write(json.dumps(item) + "\n")

# Create dataset in datastore (similar to model creation)
dataset_name = f"{MODEL_NAME}-training-data"
dataset_repo_id = f"{NAMESPACE}/{dataset_name}"

# Create dataset repository
hf_api.create_repo(dataset_repo_id, repo_type="dataset", exist_ok=True)

# Upload training data
hf_api.upload_file(
    path_or_fileobj="training_data.jsonl",
    path_in_repo="training.jsonl",
    repo_id=dataset_repo_id,
    repo_type="dataset",
    commit_message="Upload training data",
)

validation_data = [
    {
        "messages": [
            {"role": "user", "content": "How do you stay motivated?"},
            {
                "role": "assistant",
                "content": "Staying motivated involves setting clear goals, celebrating small wins, and maintaining a positive mindset even when facing challenges.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What's the capital of France?"},
            {
                "role": "assistant",
                "content": "The capital of France is Paris, a beautiful city known for its art, culture, and iconic landmarks like the Eiffel Tower.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Explain quantum physics"},
            {
                "role": "assistant",
                "content": "Quantum physics is the branch of physics that studies matter and energy at the smallest scales, where particles behave in ways that seem strange compared to our everyday experience.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What is photosynthesis?"},
            {
                "role": "assistant",
                "content": "Photosynthesis is the process by which plants convert sunlight, carbon dioxide, and water into glucose and oxygen, providing energy for the plant.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "How does the internet work?"},
            {
                "role": "assistant",
                "content": "The internet works through a global network of interconnected computers that communicate using standardized protocols to share information and resources.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What is artificial intelligence?"},
            {
                "role": "assistant",
                "content": "Artificial intelligence is the simulation of human intelligence in machines that are programmed to think, learn, and solve problems like humans.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "Describe the water cycle"},
            {
                "role": "assistant",
                "content": "The water cycle is the continuous movement of water through evaporation, condensation, precipitation, and collection that sustains life on Earth.",
            },
        ]
    },
    {
        "messages": [
            {"role": "user", "content": "What are renewable energy sources?"},
            {
                "role": "assistant",
                "content": "Renewable energy sources include solar, wind, hydroelectric, geothermal, and biomass energy that can be naturally replenished and don't deplete over time.",
            },
        ]
    },
]

# Expand validation data by repeating examples to create a larger dataset
validation_data = validation_data * 10  # 80 total examples (8 unique * 10 repetitions)

# Save validation data to JSONL file
with open("validation_data.jsonl", "w") as f:
    for item in validation_data:
        f.write(json.dumps(item) + "\n")

# Upload validation data
hf_api.upload_file(
    path_or_fileobj="validation_data.jsonl",
    path_in_repo="validation.jsonl",
    repo_id=dataset_repo_id,
    repo_type="dataset",
    commit_message="Upload validation data",
)

# Create dataset entity in Entity Store
dataset = client.datasets.create(
    name=dataset_name, namespace=NAMESPACE, files_url=f"hf://datasets/{dataset_repo_id}"
)
print(f"Created dataset entity: {dataset.namespace}/{dataset.name}")
```

---

## Start Customization Job

Start the LoRA fine-tuning job. The job will create an output artifact with the name specified in `output`, which you'll use later to access your fine-tuned model for inference.

=== "Python SDK"

    --8<-- "_snippets/input/common.py"

=== "cURL"

    ```bash
    # Create job and capture job ID
    RESPONSE=$(curl -s -X POST \
    "${NEMO_BASE_URL}/v1/customization/jobs" \
    -H 'accept: application/json' \
    -H 'Content-Type: application/json' \
    -d '{
    "name": "'${MODEL_NAME}'-lora-job",
    "config": "'${NAMESPACE}'/'${MODEL_NAME}'-lora-config@v'${MODEL_VERSION}'",
    "dataset": "'${NAMESPACE}'/'${DATASET_NAME}'",
    "output": {"name": "'${NAMESPACE}'/'${MODEL_NAME}'-lora@v'${MODEL_VERSION}'"},
    "description": "LoRA fine-tuning job for '${MODEL_NAME}'",
    "training": {
    "type": "sft",
    "peft": {
    "type": "lora",
    "rank": 16,
    "alpha": 32,
    "dropout": 0.01
    },
    "epochs": 3,
    "batch_size": 8,
    "learning_rate": 5e-5
    }
    }')

    JOB_ID=$(echo "$RESPONSE" | jq -r '.id')
    OUTPUT_NAME=$(echo "$RESPONSE" | jq -r '.spec.output.name')
    echo "Started job with ID: $JOB_ID"
    echo "Output name: $OUTPUT_NAME"
    ```

Copy the following values from the response:

- `id` (Job ID)
- `spec.output.name`

We'll need them later to monitor the job's status and access the fine-tuned model.

Check job progress:

=== "Python SDK"

    --8<-- "_snippets/input/job-monitoring.py"

=== "cURL"

    ```bash
    # Monitor job status with comprehensive handling
    while true; do
    RESPONSE=$(curl -s -X GET \
    "${NEMO_BASE_URL}/v1/customization/jobs/${JOB_ID}" \
    -H 'accept: application/json')

    STATUS=$(echo "$RESPONSE" | jq -r '.status')
    echo "Job status: $STATUS"

    if [ "$STATUS" = "completed" ]; then
    echo "Training completed successfully!"
    break
    elif [ "$STATUS" = "failed" ] || [ "$STATUS" = "cancelled" ]; then
    echo "Training finished with status: $STATUS"
    if [ "$STATUS" = "failed" ]; then
    echo "Check the job logs for error details."
    fi
    break
    elif [ "$STATUS" = "created" ] || [ "$STATUS" = "pending" ]; then
    echo "Job is queued and waiting to start..."
    elif [ "$STATUS" = "running" ]; then
    echo "Training is in progress..."
    # Optionally show progress if available
    PROGRESS=$(echo "$RESPONSE" | jq -r '.status_details.percentage_done // "N/A"')
    if [ "$PROGRESS" != "N/A" ] && [ "$PROGRESS" != "null" ]; then
    echo "Progress: ${PROGRESS}%"
    fi
    elif [ "$STATUS" = "cancelling" ]; then
    echo "Job is being cancelled..."
    elif [ "$STATUS" = "ready" ] || [ "$STATUS" = "unknown" ]; then
    echo "Job finished with status: $STATUS"
    break
    else
    echo "Unknown status: $STATUS"
    fi

    sleep 60 # Wait 1 minute before checking again
    done
    ```

---

## Test the Deployed Model

After the customization job has been completed, you can use the `output.name` to access the fine-tuned model and evaluate its performance. The base model NIM deployment you created earlier will automatically load the LoRA adapter when you specify the LoRA model ID in your inference requests.

!!! note
    The inference endpoints use the `inference_base_url` configured during client initialization (typically the NIM proxy URL). The base model deployment must be running before you can test inference with LoRA adapters.

!!! tip
    If you included a WandB API key, you can view your training results at [wandb.ai](https://wandb.ai/home) under the `nvidia-nemo-customizer` project.

=== "Python SDK"

    ```python
    base_model_id = f"{NAMESPACE}/{MODEL_NAME}"

    # Option 1: If you still have the job object from creation
    # lora_model_id = job.spec.output.name

    # Option 2: Construct from job parameters (use this if running in a new session)
    lora_model_id = f"{NAMESPACE}/{MODEL_NAME}-lora@v{MODEL_VERSION}"

    # First, check if the models are available for inference
    # Note: The base model deployment must be running and registered with the NIM proxy
    try:
    # List models from the entity store (shows all registered models)
    models_response = client.models.list()
    available_models = models_response.data

    print("Registered models:")
    for model in available_models:
    print(f" - {model.id}")

    # Test base model
    print(f"\nTesting base model: {base_model_id}")
    base_response = client.chat.completions.create(
    model=base_model_id,
    messages=[
    {
    "role": "user",
    "content": "Hello, can you help me?"
    }
    ],
    max_tokens=100,
    temperature=0.7
    )

    print("Base model response:")
    print(base_response.choices[0].message.content)

    # Test LoRA-adapted model (if available)
    print(f"\nTesting LoRA-adapted model: {lora_model_id}")
    lora_response = client.chat.completions.create(
    model=lora_model_id,
    messages=[
    {
    "role": "user",
    "content": "Hello, can you help me?"
    }
    ],
    max_tokens=100,
    temperature=0.7
    )

    print("LoRA-adapted model response:")
    print(lora_response.choices[0].message.content)

    except Exception as e:
    print(f"Error testing model: {e}")
    ```

=== "cURL"

    ```bash
    # Set the NIM proxy URL
    export NIM_PROXY_URL="http://nim.test"

    # Option 1: If you captured OUTPUT_MODEL from job creation (from earlier in tutorial)
    # export OUTPUT_MODEL="<value from job creation response>"

    # Option 2: Construct from environment variables (use this if running in a new session)
    export LORA_MODEL_ID="${NAMESPACE}/${MODEL_NAME}-lora@v${MODEL_VERSION}"

    # Test model availability
    curl -X GET "${NIM_PROXY_URL}/models" | jq

    # Test inference against the base model
    curl -X POST "${NIM_PROXY_URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{
    "model": "'${NAMESPACE}'/'${MODEL_NAME}'",
    "messages": [
    {"role": "user", "content": "Hello! How are you?"},
    {"role": "assistant", "content": "Hi! I am quite well, how can I help you today?"},
    {"role": "user", "content": "Can you write me a song?"}
    ],
    "top_p": 1,
    "n": 1,
    "max_tokens": 50,
    "frequency_penalty": 1.0
    }'

    # Test inference against a LoRA-adapted model (after customization completes)
    curl -X POST "${NIM_PROXY_URL}/v1/chat/completions" \
    -H 'Content-Type: application/json' \
    -d '{
    "model": "'${LORA_MODEL_ID}'",
    "messages": [
    {"role": "user", "content": "Hello! How are you?"},
    {"role": "assistant", "content": "Hi! I am quite well, how can I help you today?"},
    {"role": "user", "content": "Can you write me a song?"}
    ],
    "top_p": 1,
    "n": 1,
    "max_tokens": 50,
    "frequency_penalty": 1.0
    }'
    ```

## Next Steps

Learn how to [check customization job metrics](metrics.md) to monitor the training progress and performance of your fine-tuned model.
