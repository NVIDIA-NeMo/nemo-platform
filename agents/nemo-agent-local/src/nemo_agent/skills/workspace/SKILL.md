---
name: workspace
description: NeMo Platform workspace CRUD playbook through `nemo_api(resource='workspaces')`. Use for workspace creation, listing, retrieval, or deletion.
---
Workspace tasks

- Some instructions mention MCP workspace tools (`create_workspace`, `list_workspaces`).
  In AUT mode, complete the same intent with `nemo_api`.
- SDK/API operations:
  - `nemo_api(resource="workspaces", action="create", params={"name":"...", "description":"..."})`
  - `nemo_api(resource="workspaces", action="list")`
  - `nemo_api(resource="workspaces", action="retrieve", params={"name":"..."})`
  - `nemo_api(resource="workspaces", action="delete", params={"name":"..."})`
- Complete all numbered requirements before stopping.
