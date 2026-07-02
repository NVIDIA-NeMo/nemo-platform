package authz_test

import data.authz
import data.common

# Test data specifically for workspace creation scenarios
workspace_test_data := {
    "roles": {
        "Viewer": {
            "permissions": ["workspaces.read", "workspaces.list"]
        },
        "Editor": {
            "includes": ["Viewer"],
            "permissions": ["workspaces.update"]
        },
        "Admin": {
            "includes": ["Editor"],
            "permissions": ["workspaces.delete", "workspaces.members.list", "workspaces.members.create", "workspaces.members.update", "workspaces.members.delete"]
        }
    },
    "endpoints": {
        "/apis/entities/v2/workspaces": {
            "get": {"permissions": ["workspaces.list"]},
            "post": {"permissions": []}  # Empty permissions - any authenticated user can create
        },
        "/apis/entities/v2/workspaces/{name}": {
            "get": {"permissions": ["workspaces.read"]},
            "put": {"permissions": ["workspaces.update"]},
            "delete": {"permissions": ["workspaces.delete"]}
        }
    },
    "workspaces": {
        "existing-ns": {}
    },
    "principals": {
        "new-user@test.com": {
            "workspaces": {}  # User has no workspace permissions yet
        },
        "existing-user@test.com": {
            # Viewer of existing-ns plus a system Viewer grant — listing workspaces now requires
            # workspaces.list in the system workspace.
            "workspaces": {"existing-ns": ["Viewer"], "system": ["Viewer"]}
        }
    }
}

# Test that any authenticated user can create a workspace
test_authenticated_user_can_create_workspace if {
    result := authz.allow with input as {
        "principal_id": "new-user@test.com",
        "method": "POST",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals
    
    result.allowed == true
}

# Test that authenticated user without any permissions can still create workspace
test_user_without_permissions_can_create_workspace if {
    result := authz.allow with input as {
        "principal_id": "random-user@test.com",  # Not even in principals list
        "method": "POST",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals
    
    result.allowed == true
}

# Test that unauthenticated users cannot create workspaces
test_unauthenticated_user_cannot_create_workspace if {
    result := authz.allow with input as {
        "principal_id": "",  # Empty principal ID
        "method": "POST",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals
    
    result.allowed == false
}

# Test that listing workspaces requires the system-level workspaces.list permission.
test_listing_workspaces_requires_permission if {
    # existing-user@test.com holds workspaces.list in the system workspace, so it can list.
    result := authz.allow with input as {
        "principal_id": "existing-user@test.com",
        "method": "GET",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals
    
    result.allowed == true
}

test_listing_workspaces_without_permission_denied if {
    # new-user@test.com has no roles at all, so it lacks workspaces.list in the system
    # workspace and can no longer list workspaces.
    result := authz.allow with input as {
        "principal_id": "new-user@test.com",
        "method": "GET",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals

    result.allowed == false
}

# Test allow for workspace creation
test_allow_workspace_creation if {
    result := authz.allow with input as {
        "principal_id": "new-user@test.com",
        "method": "POST",
        "path": "/apis/entities/v2/workspaces"
    }
    with data.authz.roles as workspace_test_data.roles
    with data.authz.endpoints as workspace_test_data.endpoints
    with data.authz.workspaces as workspace_test_data.workspaces
    with data.authz.principals as workspace_test_data.principals
    
    result.allowed == true
}

# Test that get_required_permissions returns empty array for workspace creation
test_workspace_creation_has_no_required_permissions if {
    perms := common.get_required_permissions("/apis/entities/v2/workspaces", "POST")
        with data.authz.endpoints as workspace_test_data.endpoints
    perms == []
}
