# Roles and Permissions

The authoritative reference for {{platform_name}} roles and their permissions. For background on how RBAC works, see [Authorization Concepts](../concepts.md). For managing workspace members, see [Managing Access](managing-access.md).

## Role Descriptions

{{platform_name}} provides four predefined roles, each designed for a specific user persona:

**Viewer** — For stakeholders who need visibility into resources but should not modify them.

- View all resources in a workspace (models, datasets, jobs, evaluations)
- Run inference on deployed models
- View job logs and evaluation results
- Cannot create, update, or delete any resources

**Editor** — For team members who actively work with resources.

- All Viewer permissions
- Create, update, and delete resources (models, datasets, evaluations, jobs)
- Run customization jobs, evaluations, and data design tasks
- Cannot manage workspace members or settings

**Admin** — For workspace owners who manage their team's access.

- All Editor permissions
- Add and remove workspace members
- Change member roles
- Grant wildcard access (`*`) to the workspace
- Change workspace visibility

**PlatformAdmin** — For platform operators who manage the entire {{platform_name}} deployment. This role bypasses all workspace-level authorization.

- All Admin permissions across every workspace
- Access all workspaces regardless of role bindings
- Manage platform-level configuration
- Create and delete any workspace

## Role Hierarchy

Each role includes all permissions of the roles below it:

```text
PlatformAdmin
 ▲
 Admin (+manage_members, +change_visibility)
 ▲
 Editor (+create, +update, +delete, +cancel)
 ▲
 Viewer (list, read, inference)
```

## Permission Matrix

Rows are operations; columns are roles. A checkmark indicates the role has permission.

### Workspace Operations

| Operation | Viewer | Editor | Admin | PlatformAdmin |
|-----------|:------:|:------:|:-----:|:-------------:|
| List workspaces (visible to user) | ✓ | ✓ | ✓ | ✓ |
| Create workspace | ✓ | ✓ | ✓ | ✓ |
| Delete workspace | | | ✓ | ✓ |
| List workspace members | ✓ | ✓ | ✓ | ✓ |
| Add / remove members | | | ✓ | ✓ |
| Change workspace visibility | | | ✓ | ✓ |

!!! note
    All authenticated users can create workspaces. The creator automatically becomes Admin.

### Resource Operations (Models, Datasets, Projects)

| Operation | Viewer | Editor | Admin | PlatformAdmin |
|-----------|:------:|:------:|:-----:|:-------------:|
| List resources | ✓ | ✓ | ✓ | ✓ |
| View / read resource | ✓ | ✓ | ✓ | ✓ |
| Create resource | | ✓ | ✓ | ✓ |
| Update resource | | ✓ | ✓ | ✓ |
| Delete resource | | ✓ | ✓ | ✓ |

### Jobs (Customization, Evaluation, Data Design)

| Operation | Viewer | Editor | Admin | PlatformAdmin |
|-----------|:------:|:------:|:-----:|:-------------:|
| List jobs | ✓ | ✓ | ✓ | ✓ |
| View job / logs | ✓ | ✓ | ✓ | ✓ |
| Create / run job | | ✓ | ✓ | ✓ |
| Cancel job | | ✓ | ✓ | ✓ |
| Delete job | | ✓ | ✓ | ✓ |

### Inference

| Operation | Viewer | Editor | Admin | PlatformAdmin |
|-----------|:------:|:------:|:-----:|:-------------:|
| Run inference (chat completions, completions, embeddings) | ✓ | ✓ | ✓ | ✓ |

### Deployment

| Operation | Viewer | Editor | Admin | PlatformAdmin |
|-----------|:------:|:------:|:-----:|:-------------:|
| List deployments | ✓ | ✓ | ✓ | ✓ |
| View deployment | ✓ | ✓ | ✓ | ✓ |
| Create deployment | | ✓ | ✓ | ✓ |
| Update deployment | | ✓ | ✓ | ✓ |
| Delete deployment | | ✓ | ✓ | ✓ |

## Wildcard Principal Behavior

The wildcard principal `*` grants a role to **all authenticated users**. When both a wildcard binding and an explicit binding exist for a user in the same workspace, the highest role wins.

Example:

- Workspace `shared-data` has `*` → Viewer
- `alice@company.com` has explicit Editor binding in `shared-data`
- Alice's effective role: **Editor** (highest of Viewer and Editor)

## Default Workspace Bindings

{{platform_name}} automatically provisions wildcard bindings on built-in workspaces:

| Workspace | Wildcard Role | Effect |
|-----------|--------------|--------|
| `default` | Editor for `*` | All authenticated users can create and manage resources |
| `system` | Viewer for `*` | All authenticated users have read-only access to system resources |

## Admin Protection

Every workspace must have at least one Admin. The platform enforces this:

- You cannot remove the last Admin from a workspace
- You cannot change the last Admin's role to Viewer or Editor

To leave a workspace where you are the only Admin, add another Admin first.

## Related

- [Authorization Concepts](../concepts.md) — Workspaces, roles, bindings, and the RBAC model.
- [Managing Access](managing-access.md) — Add users, assign roles, manage workspace members.
- [API Scopes](api-scopes.md) — Token-level scope restrictions.
- [Security Model](../security-model.md) — Trust boundaries and authorization layers.
