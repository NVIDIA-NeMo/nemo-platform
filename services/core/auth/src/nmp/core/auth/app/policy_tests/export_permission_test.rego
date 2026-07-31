package authz_export_test

import data.authz
import future.keywords.if

export_roles := {
	"Viewer": {
		"permissions": ["models.read", "models.list"],
	},
	"Exporter": {
		"includes": ["Viewer"],
		"permissions": ["models.export"],
	},
	"ServiceSystem": {
		"permissions": ["*"],
	},
}

export_endpoints := {
	"/apis/models/v2/workspaces/{workspace}/models/{name}": {
		"get": {"permissions": ["models.read"]},
	},
}

export_principals := {
	"viewer@example.com": {
		"workspaces": {"source-workspace": ["Viewer"]},
	},
	"exporter@example.com": {
		"workspaces": {"source-workspace": ["Exporter"]},
	},
}

test_direct_user_read_does_not_require_export if {
	result := authz.allow
		with input as {
			"principal_id": "viewer@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == true
}

test_same_workspace_service_read_does_not_require_export if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "viewer@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
			"origin_workspace": "source-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == true
}

test_same_workspace_service_read_cannot_bypass_delegate_permissions if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "unbound@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
			"origin_workspace": "source-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == false
}

test_delegated_service_read_without_origin_is_denied if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "exporter@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == false
}

test_cross_workspace_service_read_denied_without_export if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "viewer@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
			"origin_workspace": "destination-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == false
}

test_cross_workspace_service_read_allowed_with_export if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "exporter@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
			"origin_workspace": "destination-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == true
}

test_shared_workspace_wildcard_export if {
	shared_principals := object.union(
		export_principals,
		{"*": {"workspaces": {"source-workspace": ["Exporter"]}}},
	)
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "unbound@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
			"origin_workspace": "destination-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as shared_principals

	result.allowed == true
}

test_delegated_wildcard_workspace_read_is_denied if {
	result := authz.allow
		with input as {
			"principal_id": "service:models",
			"on_behalf_of_principal_id": "exporter@example.com",
			"method": "GET",
			"path": "/apis/models/v2/workspaces/-/models/model-a",
			"origin_workspace": "destination-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as export_principals

	result.allowed == false
}

# The entities list endpoint with wildcard workspace is exempted from the
# wildcard-workspace deny rule so that cross-workspace entity queries work.
# The application layer enforces per-workspace access on the results.
test_delegated_entities_list_wildcard_allowed if {
	entity_endpoints := object.union(export_endpoints, {
		"/apis/entities/v2/workspaces/{workspace}/entities/{entity_type}": {
			"get": {"permissions": ["entities.read"]},
		},
	})
	result := authz.allow
		with input as {
			"principal_id": "service:entities",
			"on_behalf_of_principal_id": "viewer@example.com",
			"method": "GET",
			"path": "/apis/entities/v2/workspaces/-/entities/customization_config",
			"origin_workspace": "destination-workspace",
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as entity_endpoints
		with data.authz.principals as export_principals

	result.allowed == true
}

test_envoy_delegated_groups_use_on_behalf_of_identity if {
	group_principals := object.union(
		export_principals,
		{
			"delegate-exporters": {
				"workspaces": {"source-workspace": ["Exporter"]},
			},
		},
	)
	result := authz.allow
		with input as {
			"attributes": {
				"request": {
					"http": {
						"method": "GET",
						"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
						"headers": {
							"x-nmp-principal-id": "service:models",
							"x-nmp-principal-groups": "service-group",
							"x-nmp-principal-on-behalf-of": "viewer@example.com",
							"x-nmp-principal-on-behalf-of-groups": "delegate-exporters",
							"x-nmp-origin-workspace": "destination-workspace",
						},
					},
				},
			},
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as group_principals

	result.allowed == true
}

test_envoy_service_groups_cannot_authorize_delegate if {
	group_principals := object.union(
		export_principals,
		{
			"service-exporters": {
				"workspaces": {"source-workspace": ["Exporter"]},
			},
		},
	)
	result := authz.allow
		with input as {
			"attributes": {
				"request": {
					"http": {
						"method": "GET",
						"path": "/apis/models/v2/workspaces/source-workspace/models/model-a",
						"headers": {
							"x-nmp-principal-id": "service:models",
							"x-nmp-principal-groups": "service-exporters",
							"x-nmp-principal-on-behalf-of": "viewer@example.com",
							"x-nmp-principal-on-behalf-of-groups": "no-access",
							"x-nmp-origin-workspace": "destination-workspace",
						},
					},
				},
			},
		}
		with data.authz.roles as export_roles
		with data.authz.endpoints as export_endpoints
		with data.authz.principals as group_principals

	result.allowed == false
}
