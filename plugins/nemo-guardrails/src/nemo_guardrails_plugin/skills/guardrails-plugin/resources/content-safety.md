# Content Safety with a Task LLM

Self-check rails reuse the request's main LLM. For dedicated content moderation, use a content-safety classifier (e.g. `default/nvidia-llama-3-1-nemotron-safety-guard-8b-v3`) as a separate task LLM. The `content_safety` flows reference the task LLM via `$model=content_safety`, so the `models[]` entry **is** required here.

## Prerequisites

- A backend provider that serves the content-safety model entity (see the platform `inference` skill for provider / served-models setup).
- The classifier's entity ID must be auto-discovered through IGW. Resolve it with:

  ```bash
  nemo inference providers get <provider-name> --workspace default \
    --output-format json | jq -r '.served_models[].model_entity_id'
  ```

  Use the resulting `<workspace>/<entity-name>` string in `models[].model` — manually registered served-model entries are dropped by the reconciler on the next refresh.

## Config

This is the production-grade config used in `docs/guardrails/tutorials/content-safety.mdx`. The two prompts share the same 23-category taxonomy and JSON output schema — they differ only in whether the conversation block includes the agent response.

```json
{
  "models": [
    {
      "type": "content_safety",
      "engine": "nim",
      "model": "default/nvidia-llama-3-1-nemotron-safety-guard-8b-v3"
    }
  ],
  "rails": {
    "input":  {"flows": ["content safety check input $model=content_safety"]},
    "output": {"flows": ["content safety check output $model=content_safety"]}
  },
  "prompts": [
    {
      "task": "content_safety_check_input $model=content_safety",
      "content": "Task: Check if there is unsafe content in the user or agent messages in the below conversation in accordance with our safety policy with the below categories. Provide a 'safe' or 'unsafe' rating for both the user message and the agent response. If there is unsafe content, please also provide a list of violated categories according to our safety policy below.\n\n<BEGIN UNSAFE CONTENT CATEGORIES>\nS1: Violence.\nS2: Sexual.\nS3: Criminal Planning/Confessions.\nS4: Guns and Illegal Weapons.\nS5: Controlled/Regulated Substances.\nS6: Suicide and Self Harm.\nS7: Sexual (minor).\nS8: Hate/Identity Hate.\nS9: PII/Privacy.\nS10: Harassment.\nS11: Threat.\nS12: Profanity.\nS13: Needs Caution.\nS14: Other.\nS15: Manipulation.\nS16: Fraud/Deception.\nS17: Malware.\nS18: High Risk Gov Decision Making.\nS19: Political/Misinformation/Conspiracy.\nS20: Copyright/Trademark/Plagiarism.\nS21: Unauthorized Advice.\nS22: Illegal Activity.\nS23: Immoral/Unethical.\n<END UNSAFE CONTENT CATEGORIES>\n\n<BEGIN CONVERSATION>\n\nuser: {{ user_input }}\n\n<END CONVERSATION>\n\nProvide your safety assessment for the above conversation in the below output JSON format:\n{\"User Safety\": safe or unsafe rating for the user message, \"Response Safety\": safe or unsafe rating for the agent response. Omit if no agent response present. \"Safety Categories\": a comma-separated list of applicable safety categories from the provided taxonomy. Omit if all safe.}\n\nDo not include anything other than the output JSON in your response.\nOutput JSON:",
      "output_parser": "nemoguard_parse_prompt_safety",
      "max_tokens": 50
    },
    {
      "task": "content_safety_check_output $model=content_safety",
      "content": "Task: Check if there is unsafe content in the user or agent messages in the below conversation in accordance with our safety policy with the below categories. Provide a 'safe' or 'unsafe' rating for both the user message and the agent response. If there is unsafe content, please also provide a list of violated categories according to our safety policy below.\n\n<BEGIN UNSAFE CONTENT CATEGORIES>\nS1: Violence.\nS2: Sexual.\nS3: Criminal Planning/Confessions.\nS4: Guns and Illegal Weapons.\nS5: Controlled/Regulated Substances.\nS6: Suicide and Self Harm.\nS7: Sexual (minor).\nS8: Hate/Identity Hate.\nS9: PII/Privacy.\nS10: Harassment.\nS11: Threat.\nS12: Profanity.\nS13: Needs Caution.\nS14: Other.\nS15: Manipulation.\nS16: Fraud/Deception.\nS17: Malware.\nS18: High Risk Gov Decision Making.\nS19: Political/Misinformation/Conspiracy.\nS20: Copyright/Trademark/Plagiarism.\nS21: Unauthorized Advice.\nS22: Illegal Activity.\nS23: Immoral/Unethical.\n<END UNSAFE CONTENT CATEGORIES>\n\n<BEGIN CONVERSATION>\n\nuser: {{ user_input }}\n\nresponse: agent: {{ bot_response }}\n\n<END CONVERSATION>\n\nProvide your safety assessment for the above conversation in the below output JSON format:\n{\"User Safety\": safe or unsafe rating for the user message, \"Response Safety\": safe or unsafe rating for the agent response. Omit if no agent response present. \"Safety Categories\": a comma-separated list of applicable safety categories from the provided taxonomy. Omit if all safe.}\n\nDo not include anything other than the output JSON in your response.\nOutput JSON:",
      "output_parser": "nemoguard_parse_response_safety",
      "max_tokens": 50
    }
  ]
}
```

## Wiring it up

Save the JSON above as `content-safety.json`, then create the config and attach it to a VirtualModel for full coverage:

```bash
nemo guardrail configs create content-safety \
  --workspace default \
  --description "Content-safety task LLM on input and output" \
  --input-file content-safety.json

nemo virtual-models create vm-content-safety \
  --workspace default \
  --models '[{"model":"default/<backend-model>","backend_format":"OPENAI_CHAT"}]' \
  --request-middleware '[{"name":"nemo-guardrails","config_type":"guardrail_config","config_id":"default/content-safety"}]' \
  --response-middleware '[{"name":"nemo-guardrails","config_type":"guardrail_config","config_id":"default/content-safety"}]'
```

## Notes on parsers

- `nemoguard_parse_prompt_safety` consumes the input-rail JSON verdict (`User Safety`).
- `nemoguard_parse_response_safety` consumes the output-rail JSON verdict (`Response Safety`).

If the classifier returns a value the parser can't decode (free-text instead of JSON, an unrecognized verdict label), the flow treats the response as unsafe and blocks. Verify the classifier endpoint with `nemo guardrail check` before binding the config to production VirtualModels.
