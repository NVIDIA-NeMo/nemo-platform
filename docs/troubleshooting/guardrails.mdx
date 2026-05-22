# Troubleshooting {{ngm_short_name}}

Use this documentation to troubleshoot issues that can arise when you work with [{{ngm_long_name}}].

## API Catalog Endpoint Issues

Several sample configurations in the documentation use NIMs with model endpoints hosted at <https://integrate.api.nvidia.com/v1>.
The purpose of using the endpoints is to avoid deploying NIMs locally to reduce the initial effort to get started.

Perform the following steps to troubleshoot configurations that use model endpoints from the API catalog:

1. Set an environment variable for your NVIDIA API key:

 ```console
 $ export NVIDIA_API_KEY=<nvapi-...>
 ```

1. Access a model, such as the Llama 3.1 8B NemoGuard Content Safety, from the model endpoint:

 --8<-- "troubleshooting/_snippets/input/guardrails-cmds.sh"

 ??? "Example Output"

 --8<-- "troubleshooting/_snippets/output/guardrails-content-safety.json"

 If your request is not successful, such as a 401 or 403 HTTP status code,
 go to <https://build.nvidia.com/settings/api-keys> to generate a new API key.

1. Access other models.
 In the preceding sample `curl` command, replace the `model` value with one of the following:

 - `nvidia/llama-3.1-nemoguard-8b-content-safety`
 - `meta/llama-3.1-8b-instruct`

 If you are able to access the model endpoints successfully, review the `config.yml`, Colang, and
 Python files in your configuration store to continue troubleshooting.

## Troubleshooting Issues with Self-Check Rails

The self-check input and output rails rely on using the main LLM as a judge.
When using models with limited reasoning capacity--typically less than 8B parameters--sometimes the main LLM does not have enough knowledge to judge appropriately.

If you experience safe queries that are blocked, consider the following suggestions:

- Use a larger LLM that has more reasoning capacity.
- Revise the self-check prompt to be more precise about what content to block, or more permissive about topics to permit.
