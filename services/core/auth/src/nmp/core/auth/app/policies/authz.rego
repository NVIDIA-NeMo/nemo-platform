package authz

import future.keywords.contains
import future.keywords.if
import future.keywords.in

import data.authz.extract_method
import data.authz.extract_path
import data.authz.extract_scopes
import data.authz.extract_workspace_from_path
import data.authz.scope_check_passed
import data.common.get_applicable_principals
import data.common.get_required_permissions
import data.common.has_permissions
import data.common.normalize_endpoint
import data.common.path_matches_pattern

# Main entry point - returns result with X-NMP-Authorized header
#
# Example input:
# {
#   "principal_id": "user@example.com",
#   "method": "GET",
#   "path": "/v1/models"
# }
#
# Example output:
# {
#   "allowed": true,
#   "headers": {
#     "X-NMP-Authorized": "true"
#   }
# }
allow := result if {
	allow_request
	not deny_request
	result := {"allowed": true, "headers": {"X-NMP-Authorized": "true"}}
} else := result if {
	result := {"allowed": false, "headers": {"X-NMP-Authorized": "false"}}
}

# ALLOW REQUEST RULES

# Default deny
default allow_request := false

# Platform admin bypass - has access to everything (if any principal is a platform admin)
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check if any principal is a platform admin
	some principal in applicable_principals
	"PlatformAdmin" in data.authz.principals[principal].workspaces.system
}

# Service principals on paths that do not match any configured API pattern (e.g. legacy /v1/...).
# Known paths are authorized via the ServiceSystem role (wildcard permission) and has_permissions.
allow_request if {
	principal_id := extract_principal_id
	startswith(principal_id, "service:")
	path := extract_path
	base_path := split(path, "?")[0]
	matching_patterns := {p |
		some p in object.keys(data.authz.endpoints)
		path_matches_pattern(base_path, p)
	}
	count(matching_patterns) == 0
}

# Allow if any applicable principal has required permissions and scopes (if provided)
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check scopes first (faster)
	scope_check_passed

	path := extract_path
	method := extract_method
	required_permissions := get_required_permissions(path, method)
	count(required_permissions) > 0

	workspace := extract_workspace_from_path(path)

	# Skip this rule for wildcard workspace - use cross-workspace rule instead
	workspace != "-"

	# Check if any principal has the required permissions
	some principal in applicable_principals
	has_permissions(principal, workspace, required_permissions)
}

# Wildcard workspace "-" with mutating methods: permission-based authorization.
# GET/HEAD for "-" use cross-workspace rules above; mutating methods were previously
# allowed only via unconditional service bypass (service:* defaults to ServiceSystem with "*").
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check scopes first (faster)
	scope_check_passed

	path := extract_path
	method := extract_method
	required_permissions := get_required_permissions(path, method)
	count(required_permissions) > 0

	workspace := extract_workspace_from_path(path)
	workspace == "-"
	method in ["POST", "PUT", "PATCH", "DELETE"]

	some principal in applicable_principals
	startswith(principal, "service:")
	has_permissions(principal, workspace, required_permissions)
}

# IAM APIs under /apis/auth/v2/iam/ — patterns have no {workspace} placeholder, so
# extract_workspace_from_path is undefined and workspace-scoped rules do not apply.
# Check permissions against the system workspace (PlatformAdmin, ServiceSystem *, etc.).
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0
	scope_check_passed
	path := extract_path
	base_path := split(path, "?")[0]
	startswith(base_path, "/apis/auth/v2/iam/")
	method := extract_method
	required_permissions := get_required_permissions(path, method)
	count(required_permissions) > 0
	not extract_workspace_from_path(path)
	some principal in applicable_principals
	has_permissions(principal, "system", required_permissions)
}

# Allow cross-workspace LIST operations (GET/HEAD without workspace in path)
# for authenticated users.
# If the user has no accessible workspaces, they will get empty list.
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check scopes first (faster)
	scope_check_passed

	method := extract_method
	method in ["GET", "HEAD"]
	path := extract_path

	# Ensure the path matches a known endpoint pattern.
	# normalize_endpoint is undefined for unknown paths, failing the rule (deny by default).
	normalize_endpoint(path)

	# Match if no workspace can be extracted from path (undefined = no workspace placeholder)
	not extract_workspace_from_path(path)
}

# Allow cross-workspace LIST operations with "-" wildcard workspace
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check scopes first (faster)
	scope_check_passed

	method := extract_method
	method in ["GET", "HEAD"]
	path := extract_path

	# Match if workspace is "-" wildcard
	workspace := extract_workspace_from_path(path)
	workspace == "-"
}

# Allow if endpoint explicitly has no required permissions (e.g., workspace creation)
# but still require authentication (at least one principal).
#
# SECURITY: We check the endpoint config directly instead of using get_required_permissions,
# because we need to distinguish between:
#   - endpoints explicitly configured with `permissions: []` → allow (e.g., workspace creation)
#   - endpoints not in the config at all (unknown) → deny (fail-closed)
# If normalize_endpoint cannot match the path, it is undefined, the rule body fails,
# and access is denied.
allow_request if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0

	# Check scopes first (faster)
	scope_check_passed
	path := extract_path
	method := extract_method
	endpoint := normalize_endpoint(path)
	method_lower := lower(method)
	data.authz.endpoints[endpoint][method_lower].permissions == []
}

# DENY REQUEST RULES

# Default allow (deny_request overrides allow_request when true)
default deny_request := false

# Deny direct secret value access for non-service principals (including PlatformAdmin).
# Secret values must only be accessed through the service delegation pattern, where a
# service principal reads the value on behalf of a user with secrets.access permission.
# Matches: /apis/secrets/v2/workspaces/{workspace}/secrets/{name}/access
deny_request if {
	path := extract_path
	base_path := split(path, "?")[0]
	path_parts := split(base_path, "/")
	count(path_parts) == 9
	path_parts[4] == "workspaces"
	path_parts[6] == "secrets"
	path_parts[8] == "access"

	principal_id := extract_principal_id
	not startswith(principal_id, "service:")
}

# OPA policy bundle download: system-scoped iam.bundle.read only (see static-authz endpoints).
# Without this deny, the cross-workspace GET rule would allow any authenticated user for this path.
default bundle_access_ok := false

bundle_access_ok if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0
	scope_check_passed
	some principal in applicable_principals
	has_permissions(principal, "system", ["iam.bundle.read"])
}

deny_request if {
	path := extract_path
	base_path := split(path, "?")[0]
	base_path == "/apis/auth/v2/iam/opa-bundle.tar.gz"
	not bundle_access_ok
}

# Nested Entities APIs (not workspace list/create or single-workspace CRUD): only service
# principals and PlatformAdmin (same as previous middleware: IAM paths stayed service-only).
default nested_entities_internal_only := false

nested_entities_internal_only if {
	path := extract_path
	base_path := split(path, "?")[0]
	startswith(base_path, "/apis/entities/v2/")
	not entities_workspace_object_path(base_path, extract_method)
}

deny_request if {
	nested_entities_internal_only
	principal_id := extract_principal_id
	not startswith(principal_id, "service:")
	not platform_admin_in_system
}

# True when any applicable principal has PlatformAdmin in the system workspace (see allow_request).
default platform_admin_in_system := false

platform_admin_in_system if {
	applicable_principals := get_applicable_principals
	count(applicable_principals) > 0
	some principal in applicable_principals
	"PlatformAdmin" in data.authz.principals[principal].workspaces.system
}

entities_workspace_object_path(base_path, method) if {
	parts := [p | p := split(base_path, "/")[_]; p != ""]
	count(parts) == 4
	parts[0] == "apis"
	parts[1] == "entities"
	parts[2] == "v2"
	parts[3] == "workspaces"
	lower(method) in ["get", "post"]
}

entities_workspace_object_path(base_path, method) if {
	parts := [p | p := split(base_path, "/")[_]; p != ""]
	count(parts) == 5
	parts[0] == "apis"
	parts[1] == "entities"
	parts[2] == "v2"
	parts[3] == "workspaces"
	lower(method) in ["get", "put", "delete"]
}

# Workspace-scoped sub-resources (members, projects, entities/...) are user-facing CRUD, not
# internal-only nested APIs. Without this, 6+ segment paths only hit nested_entities_internal_only
# (403 for non-service users). Cross-workspace queries use workspace "-"; exclude that.
entities_workspace_object_path(base_path, method) if {
	parts := [p | p := split(base_path, "/")[_]; p != ""]
	count(parts) >= 6
	parts[0] == "apis"
	parts[1] == "entities"
	parts[2] == "v2"
	parts[3] == "workspaces"
	parts[4] != "-"
	sub := parts[5]
	sub in ["members", "projects", "entities"]
	lower(method) in ["get", "post", "put", "patch", "delete", "head"]
}

# Health check endpoints - always allow (must match middleware HEALTH_ENDPOINTS)
allow_request if {
	path := extract_path
	path in ["/health/live", "/health/ready", "/status", "/metrics"]
}

# Deny all non-health requests when no endpoint data is loaded (fail-closed).
# Defense in depth: the WASM engine also blocks evaluation when data is not set,
# but this rule catches the case where set_data() was called with empty/partial data.
# Health endpoints are excluded so Kubernetes probes still work during startup.
deny_request if {
	count(data.authz.endpoints) == 0
	path := extract_path
	not path in ["/health/live", "/health/ready", "/status", "/metrics", "/cluster-info"]
}
