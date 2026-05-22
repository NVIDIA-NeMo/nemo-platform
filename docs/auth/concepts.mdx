# Authorization Concepts

{{platform_name}} uses **workspace-scoped RBAC**: resources live in workspaces, users get roles (Viewer, Editor, Admin) per workspace, and a policy engine evaluates every request against role bindings and token scopes.

For the security architecture and trust boundaries, see [Security Model](security-model.md). For hands-on setup, see [Managing Access](authorization/managing-access.md).

## Authorization Model Overview

The model has four building blocks:

1. **Workspaces** — containers that own resources (models, datasets, jobs)
2. **Roles** — permission bundles (Viewer, Editor, Admin) granted to users per workspace
3. **Role bindings** — the link between a user, a role, and a workspace
4. **Scopes** — token-level restrictions on top of role permissions (see [API Scopes](authorization/api-scopes.md))

## Workspaces

**Workspaces** are the authorization boundary. Every resource (model, dataset, job, etc.) belongs to exactly one workspace, and access is controlled at the workspace level. When you create a workspace, you automatically become its Admin.

### Workspace Access Levels

Workspaces can have different access levels based on role bindings:

- **Private**: Only explicitly granted members can access (no wildcard binding)
- **Shared read-only**: All authenticated users can view resources (Viewer role for `*`)
- **Shared read-write**: All authenticated users can create and modify resources (Editor role for `*`)

## Principals

**Principals** represent authenticated identities that can access the platform. Principals are typically human users identified by their email address.

Each principal can have different roles in different workspaces:

```text
alice@company.com:
 - Admin in workspace "team-ml"
 - Editor in workspace "shared-datasets"
 - Viewer in workspace "prod-models"
```

### Wildcard Principal

The special principal `*` (asterisk) represents **all authenticated users**. Granting a role to `*` in a workspace gives that access level to everyone who authenticates with the platform.

This is the mechanism for creating shared workspaces:

```text
Workspace: "shared-datasets"
├── Role Binding: principal="*", role="Viewer" # Everyone can read
└── Role Binding: principal="alice@company.com", role="Admin" # Alice manages
```

When both a wildcard binding and an explicit binding exist for a user, the highest role wins.

## Roles

**Roles** are named collections of permissions. When you grant a role to a principal in a workspace, they receive all permissions included in that role.

The predefined roles form a hierarchy — each role includes all permissions of the roles below it:

```text
PlatformAdmin (all operations across all workspaces)
 ▲
 Admin (+ manage members, change visibility)
 ▲
 Editor (+ create, update, delete resources)
 ▲
 Viewer (list, read, run inference)
```

Custom roles can be defined at deployment time with arbitrary permission sets — they do not need to follow this hierarchy. For the complete permission matrix, see [Roles & Permissions](authorization/roles-and-permissions.md).

### Predefined Roles

**Viewer** — Read-only access

- List and view all resources in the workspace
- Run inference on deployed models
- View evaluation results, job logs, and other workspace resources
- Cannot create, update, or delete resources

**Editor** — Read and write access

- All Viewer permissions
- Create, update, and delete resources
- Run evaluations, customization jobs, and other operations
- Cannot manage workspace settings or members

**Admin** — Full workspace control

- All Editor permissions
- Manage workspace members (add/remove users, assign roles)
- Grant access to all users via the wildcard principal `*`
- Full administrative control over the workspace

### Platform Admin Role

The **PlatformAdmin** role is a special highly privileged role that provides full access to all workspaces and all operations across the entire platform. This role is typically reserved for platform operators.

Platform admins can:

- Access all workspaces regardless of explicit role grants
- Manage global platform configuration
- Create and delete any workspace
- Bypass all authorization checks

The PlatformAdmin role is granted via the `admin_email` config setting. See [Auth Configuration](deployment/configuration.md).

## Role Bindings

**Role bindings** associate a principal with a role in a specific workspace. This is how you actually grant access.

A role binding contains:

- **Principal**: The user being granted access (e.g., `alice@company.com`)
- **Workspace**: The workspace where access is granted (e.g., `team-ml`)
- **Role**: The role being assigned (e.g., `Editor`)

```text
Workspace: "team-ml-research"
├── Role Binding 1
│ ├── Principal: "alice@company.com"
│ └── Role: "Admin"
│
├── Role Binding 2
│ ├── Principal: "bob@company.com"
│ └── Role: "Editor"
│
└── Role Binding 3
 ├── Principal: "charlie@company.com"
 └── Role: "Viewer"
```

## Automatic Role Assignment

### Workspace Creation

Creating a workspace is a special operation:

- All authenticated users can create workspaces (no special permission needed)
- The creator automatically receives the **Admin** role
- New workspaces are private by default (only the creator has access)
- You can immediately start creating resources

### Default Workspaces

{{platform_name}} automatically provisions role bindings for the wildcard principal `*` on certain workspaces:

- **`default`**: All authenticated users have **Editor** role, allowing everyone to create and manage resources immediately
- **`system`**: All authenticated users have **Viewer** role, providing read-only access to system-level resources

## Workspace Visibility

Users only see workspaces they have access to. When listing workspaces, the API returns only workspaces where the user has at least one role binding (direct or via wildcard `*`).

If a user tries to access a workspace they don't have permission for, the API returns `403 Forbidden` rather than `404 Not Found`. This is intentional security behavior — it avoids revealing whether a workspace exists to unauthorized users.

## Policy Decision Point (PDP)

Every authorized request is evaluated by the PDP, which checks role bindings and scopes. The PDP runs in one of two modes:

- **Embedded** (default): A WASM-based policy engine built into the auth service. No external dependencies.
- **External OPA**: An Open Policy Agent instance (sidecar or standalone service) fetches policy bundles from the auth service.

For technical details on the policy engine, see [Policy Engine](authorization/policy-engine.md). For configuration, see [Auth Configuration](deployment/configuration.md).

### Role Propagation Delay

When you add or remove a member, the change takes effect after the next policy data refresh — up to 30 seconds by default. The `members` API waits for propagation before returning (`wait_role_propagation=true`), so CLI and SDK calls block until the change is live. Direct API callers who set `wait_role_propagation=false` should account for the delay.

## Related

- [Security Model](security-model.md) — Architecture, trust boundaries, and authorization layers.
- [Roles & Permissions](authorization/roles-and-permissions.md) — Complete permission matrix.
- [API Scopes](authorization/api-scopes.md) — Token-level scope restrictions.
- [Managing Access](authorization/managing-access.md) — Add users to workspaces and assign roles.
- [Policy Engine](authorization/policy-engine.md) — OPA/WASM policy engine internals.
