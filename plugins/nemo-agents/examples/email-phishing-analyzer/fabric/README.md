# NAT Through NeMo Fabric

This example keeps the NAT workflow YAML authoritative and invokes it through
the Platform-owned NAT Fabric adapter.

From the repository root:

```bash
uvx uv@0.9.14 pip install -e "plugins/nemo-agents[fabric]"
export NVIDIA_API_KEY="<your NVIDIA API key>"

nemo agents invoke \
  --agent-config plugins/nemo-agents/examples/email-phishing-analyzer/fabric/agent.yaml \
  --input "Subject: Verify your account. Send your password immediately."
```
