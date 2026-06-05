!!! note
    `nemo setup` pre-configures a `default/nvidia-build` model provider during local startup.
    This provider routes inference requests to models hosted on `build.nvidia.com` using the API base URL `https://integrate.api.nvidia.com`
    and the NGC API key with `Public API Endpoints` permissions provided during deployment.

    You can verify this provider exists by running `nemo inference providers list --workspace default`.

    The tutorials in these docs use this provider for inference, but you can alternatively create your own and use it instead.
