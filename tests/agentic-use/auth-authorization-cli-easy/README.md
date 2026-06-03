# Authorization Flow CLI Test

This Harbor test verifies that Claude Code can perform authorization and role-based access control operations using the `nemo` CLI.

## Purpose

Tests the complete member management lifecycle within a workspace: adding members with different roles (Viewer, Editor, Admin), updating roles, and removing members. The verifier uses the `iam.role_bindings` API to confirm that role transitions actually happened by checking the audit trail of granted and revoked bindings.

## Test Flow

1. Claude Code creates workspace `harbor-auth-test` (creator becomes Admin)
2. Claude confirms creator Admin status by listing members
3. Claude adds three members with different roles: Viewer, Editor, Admin
4. Claude updates viewer@test.com from Viewer to Editor
5. Claude removes editor@test.com
6. Claude lists members to confirm final state

## Verification

The verifier checks:
- **Current state** via `workspaces.members.list()`: viewer=Editor, admin=Admin, editor removed
- **Transition history** via `iam.role_bindings.list()`:
  - viewer@test.com has a **revoked** Viewer binding (proves original role)
  - viewer@test.com has an **active** Editor binding (proves promotion)
  - editor@test.com has **only revoked** bindings (proves they existed then were removed)
  - admin@test.com has an **active** Admin binding

## CLI Commands Used

```bash
nemo workspaces create harbor-auth-test --description "Workspace for authorization testing"
nemo workspaces members list --workspace harbor-auth-test
nemo workspaces members create --principal viewer@test.com --roles Viewer --workspace harbor-auth-test
nemo workspaces members create --principal editor@test.com --roles Editor --workspace harbor-auth-test
nemo workspaces members create --principal admin@test.com --roles Admin --workspace harbor-auth-test
nemo workspaces members update viewer@test.com --roles Editor --workspace harbor-auth-test
nemo workspaces members delete editor@test.com --workspace harbor-auth-test
```
