# Managing Access

Add users to workspaces, assign roles, and control who can access your resources. For background on the authorization model, refer to [Authorization Concepts](../concepts.md). For what each role can do, refer to [Roles & Permissions](roles-and-permissions.md).

!!! note
    The SDK examples on this page use `NeMoPlatform()` with no arguments so that the client reads your active CLI context (set by `nemo auth login`). That is the right pattern for authorization workflows: you act as your logged-in identity and pass the workspace explicitly in each API call. For the standard local initialization pattern, see [CLI and SDK initialization](../../get-started/setup.md#setup-init).

## Creating Workspaces

Workspaces are the primary authorization boundary — all resources belong to a workspace, and access is controlled at the workspace level. When you create a workspace, you automatically become its Admin.

Create separate workspaces to isolate teams (`ml-research`, `nlp-team`), environments (`dev`, `staging`, `prod`), or projects. For detailed workspace management, refer to [Workspaces](../../get-started/concepts/workspaces.md).


=== "CLI"

    ```bash
    nemo workspaces create ml-team

    # Set the workspace as your default for subsequent commands
    nemo config set --workspace ml-team
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    workspace = client.workspaces.create(
        name="ml-team", description="Machine learning team workspace"
    )
    ```

## Managing Workspace Members

Members are users who have been granted access to a workspace. Each member has one of three roles:

- **Viewer** — Read-only access to all resources
- **Editor** — Can create, modify, and delete resources
- **Admin** — Full control, including managing members

!!! note
    **Role Propagation**

    When you add or change a member, the CLI and SDK wait for the change to propagate to the authorization engine before returning (up to 30 seconds). The member can use their new permissions immediately after the command completes.

### Add a Member

Grant someone access to a workspace by adding them as a member with a specific role. The principal is typically an email address that identifies the user in your identity provider.


=== "CLI"

    ```bash
    nemo members create --principal alice@example.com --roles Editor
    ```

    ```json
    {
      "principal": "alice@example.com",
      "roles": [
        "Editor"
      ],
      "granted_at": "2026-01-20T10:00:00Z",
      "granted_by": "admin@example.com"
    }
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    # Add a member with Editor role
    client.members.create(
        workspace="ml-team", principal="alice@example.com", roles=["Editor"]
    )

    # Add a member with Viewer role (read-only)
    client.members.create(
        workspace="ml-team", principal="bob@example.com", roles=["Viewer"]
    )

    # Add a member with Admin role (full control)
    client.members.create(
        workspace="ml-team", principal="charlie@example.com", roles=["Admin"]
    )
    ```

### List Members

View all members of a workspace to audit access or verify permissions. The response includes each member's principal, roles, and when access was granted.


=== "CLI"

    ```bash
    nemo members list
    ```

    ```json
    [
      {
        "principal": "alice@example.com",
        "roles": [
          "Editor"
        ],
        "granted_at": "2026-01-20T10:00:00Z",
        "granted_by": "admin@example.com"
      },
      {
        "principal": "bob@example.com",
        "roles": [
          "Viewer"
        ],
        "granted_at": "2026-01-20T10:01:00Z",
        "granted_by": "admin@example.com"
      },
      {
        "principal": "charlie@example.com",
        "roles": [
          "Admin"
        ],
        "granted_at": "2026-01-20T10:02:00Z",
        "granted_by": "admin@example.com"
      }
    ]
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    members = client.members.list(workspace="ml-team")

    for member in members.data:
    print(f"{member.principal}: {member.roles}")
    ```

### Update Member Roles

Change a member role to adjust their permissions, for example, promoting a Viewer to Editor when they need to create resources.


=== "CLI"

    ```bash
    nemo members update bob@example.com --roles Editor
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    # Promote a Viewer to Editor
    client.members.update(
        workspace="ml-team", principal_id="bob@example.com", roles=["Editor"]
    )
    ```

### Remove a Member

Revoke a member's access by removing them from the workspace. This removes all their role bindings in the workspace — they will no longer be able to access any resources unless re-added.


=== "CLI"

    ```bash
    nemo members delete alice@example.com
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    client.members.delete(workspace="ml-team", principal_id="alice@example.com")
    ```

## Granting Access to All Users

Use the wildcard principal `*` to grant a role to all authenticated users. This is useful for shared workspaces where you want broad access without adding each user individually.

Common use cases:

- **Shared datasets** — Grant Viewer to `*` so everyone can use common training data
- **Team shared space** — Grant Editor to `*` for a workspace where anyone can experiment
- **Published models** — Grant Viewer to `*` for production models that everyone should access

### Make a Workspace Readable by Everyone

Grant the Viewer role to `*` so all authenticated users can view resources.


=== "CLI"

    ```bash
    nemo members create --principal "*" --roles Viewer
    ```

    ```json
    {
      "principal": "*",
      "roles": [
        "Viewer"
      ],
      "granted_at": "2026-01-20T10:05:00Z",
      "granted_by": "admin@example.com"
    }
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    client.members.create(workspace="shared-models", principal="*", roles=["Viewer"])
    ```

### Make a Workspace Editable by Everyone

Grant the Editor role to `*` so all authenticated users can create and modify resources.


=== "CLI"

    ```bash
    nemo members create --principal "*" --roles Editor
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    client.members.create(workspace="shared-datasets", principal="*", roles=["Editor"])
    ```

### Remove Public Access

Remove the wildcard binding to restrict the workspace to explicit members only.


=== "CLI"

    ```bash
    nemo members delete "*"
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    client.members.delete(workspace="ml-team", principal_id="*")
    ```

!!! note
    **Default Workspace Access**

    The platform automatically grants wildcard access to built-in workspaces:

    - `default` workspace: All users have **Editor** access
    - `system` workspace: All users have **Viewer** access (read-only)

    This allows users to start working immediately without explicit role assignment.

## Admin Protection

Every workspace must have at least one Admin to prevent orphaned workspaces. The platform enforces this rule:

- You cannot remove the last Admin from a workspace
- You cannot change the last Admin's role to Viewer or Editor

If you need to leave a workspace where you are the only Admin, add another Admin first:


=== "CLI"

    ```bash
    # Add another admin first
    nemo members create --principal charlie@example.com --roles Admin

    # Now you can remove yourself
    nemo members delete alice@example.com
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform

    client = NeMoPlatform()

    # Add another admin first
    client.members.create(
        workspace="ml-team", principal="charlie@example.com", roles=["Admin"]
    )

    # Now you can remove yourself
    client.members.delete(workspace="ml-team", principal_id="alice@example.com")
    ```

## Platform Admin Access

The **PlatformAdmin** role (set using `admin_email` in config) has full access to all workspaces and bypasses authorization checks. PlatformAdmin is typically used for initial platform setup, creating the first workspaces and granting Admin roles to team leads. After bootstrap, day-to-day access management should use workspace-level members (above).

For details on configuring the platform admin, refer to [Auth Configuration](../deployment/configuration.md). For the full security implications, refer to [Security Model](../security-model.md).

## Deleting Workspaces

Admins can delete workspaces they manage. However, a workspace cannot be deleted if it contains resources (projects, datasets, models, and so on). The API returns a `409 Conflict` error listing which entity types exist:

```json
{
  "detail": "Cannot delete workspace 'ml-team': workspace contains entities that must be deleted first: project (3), dataset (5)"
}
```

Delete all resources in the workspace before deleting the workspace itself:


=== "CLI"

    ```bash
    # List and delete projects first
    nemo projects list --workspace ml-team
    nemo projects delete my-project --workspace ml-team

    # Then delete the workspace
    nemo workspaces delete ml-team
    ```

=== "Python SDK"

    ```python
    from nemo_platform import NeMoPlatform, ConflictError

    client = NeMoPlatform()

    try:
    client.workspaces.delete("ml-team")
    except ConflictError as e:
    print(f"Cannot delete workspace: {e}")
    # Delete resources first, then retry
    projects = client.projects.list(workspace="ml-team")
    for project in projects.data:
    client.projects.delete(project.name, workspace="ml-team")
    # Now delete the workspace
    client.workspaces.delete("ml-team")
    ```
