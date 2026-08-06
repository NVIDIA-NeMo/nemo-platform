---
name: secrets
description: NeMo Platform secret CRUD lifecycle through the platform SDK.
---
Secret tasks

- Use `nemo_api` with resource `secrets`.
- Use `create`, `retrieve`, `list`, `update`, and `delete` actions as needed,
  passing secret data directly in the JSON `params`.
- Always finish the whole lifecycle: create temporary secret, verify/list/update/delete it, then create the final verification secret.
