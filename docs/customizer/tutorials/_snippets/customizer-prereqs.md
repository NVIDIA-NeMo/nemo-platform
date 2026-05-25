# NeMo Customizer Prerequisites

??? "Platform Setup Requirements and Environment Variables"
    :icon: gear

    Before starting, make sure you have:

    - {{platform_name}} installed and deployed (see [Setup](../../get-started/setup.md))
    - The `nemo-platform` Python SDK installed (`pip install nemo-platform[services]`)
    - (Optional) Weights & Biases account and API key for enhanced visualization

    **Set up environment variables:**

    ```bash
    # Set the base URL for {{platform_name}}
    export NMP_BASE_URL="http://localhost:8080" # Or your deployed platform URL

    # Optional: Weights & Biases for experiment tracking
    export WANDB_API_KEY="<your-wandb-api-key>"
    ```

    **Initialize the SDK:**

    ```python
    import os
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform(
        base_url=os.environ.get("NMP_BASE_URL", "http://localhost:8080"),
        workspace="default",
    )
    ```
