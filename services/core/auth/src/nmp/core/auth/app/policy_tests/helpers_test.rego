package authz_test

import data.authz
import data.common

# Test helper functions

# Test workspace extraction from path
test_extract_workspace_from_path if {
    # Define mock endpoint patterns for testing (aligned with /apis/.../v2 routes)
    mock_endpoints := {
        "/apis/entities/v2/workspaces/{workspace}/members": {"get": {}},
        "/apis/models/v2/workspaces/{workspace}/models/{name}": {"get": {}},
        "/apis/files/v2/workspaces/{workspace}/filesets/{name}": {"get": {}}
    }
    
    # Test various path patterns
    authz.extract_workspace_from_path("/apis/entities/v2/workspaces/my-workspace/members") == "my-workspace"
        with data.authz.endpoints as mock_endpoints
    authz.extract_workspace_from_path("/apis/models/v2/workspaces/my-workspace/models/model-123") == "my-workspace"
        with data.authz.endpoints as mock_endpoints
    authz.extract_workspace_from_path("/apis/files/v2/workspaces/test-ns/filesets/dataset-456") == "test-ns"
        with data.authz.endpoints as mock_endpoints
}

# Test endpoint normalization
test_normalize_endpoint if {
    # Define mock endpoint patterns for testing
    mock_endpoints := {
        "/apis/models/v2/workspaces/{workspace}/models": {"get": {}},
        "/apis/models/v2/workspaces/{workspace}/models/{name}": {"get": {}},
        "/apis/files/v2/workspaces/{workspace}/filesets/{name}": {"get": {}},
        "/apis/entities/v2/workspaces": {"get": {}},
        "/apis/entities/v2/workspaces/{workspace}/members": {"get": {}},
        "/apis/evaluation/v2/workspaces/{workspace}/benchmarks/{name}": {"get": {}}
    }
    
    # Test pattern matching for models
    common.normalize_endpoint("/apis/models/v2/workspaces/test-ns/models/model-name") == "/apis/models/v2/workspaces/{workspace}/models/{name}"
        with data.authz.endpoints as mock_endpoints
    
    # Test pattern matching for filesets
    common.normalize_endpoint("/apis/files/v2/workspaces/my-ns/filesets/dataset-123") == "/apis/files/v2/workspaces/{workspace}/filesets/{name}"
        with data.authz.endpoints as mock_endpoints
    
    # Test pattern matching for workspace members
    common.normalize_endpoint("/apis/entities/v2/workspaces/789/members") == "/apis/entities/v2/workspaces/{workspace}/members"
        with data.authz.endpoints as mock_endpoints
    
    # Test exact matches
    common.normalize_endpoint("/apis/models/v2/workspaces/ws/models") == "/apis/models/v2/workspaces/{workspace}/models"
        with data.authz.endpoints as mock_endpoints
    common.normalize_endpoint("/apis/entities/v2/workspaces") == "/apis/entities/v2/workspaces"
        with data.authz.endpoints as mock_endpoints
    
    # Test evaluation benchmarks pattern
    common.normalize_endpoint("/apis/evaluation/v2/workspaces/test-ns/benchmarks/my-config") == "/apis/evaluation/v2/workspaces/{workspace}/benchmarks/{name}"
        with data.authz.endpoints as mock_endpoints
}

test_extract_domain_name_from_core_path if {
    authz.extract_domain_name("/apis/models/v2/workspaces/default/models") == "models"
}

test_extract_domain_name_from_extension_path if {
    authz.extract_domain_name("/apis/agents/v2/workspaces/default/agents") == "agents"
}

test_get_domain_metadata_returns_core_domain if {
    mock_domains := {
        "models": {"name": "models", "version": "core", "kind": "core"},
        "agents": {"name": "agents", "version": "1.2.3", "kind": "extension"}
    }

    domain := common.get_domain_metadata("/apis/models/v2/workspaces/default/models")
        with data.authz.domains as mock_domains
    domain.name == "models"
    domain.version == "core"
    domain.kind == "core"
}

test_get_domain_metadata_returns_extension_domain if {
    mock_domains := {
        "models": {"name": "models", "version": "core", "kind": "core"},
        "agents": {"name": "agents", "version": "1.2.3", "kind": "extension"}
    }

    domain := common.get_domain_metadata("/apis/agents/v2/workspaces/default/agents")
        with data.authz.domains as mock_domains
    domain.name == "agents"
    domain.version == "1.2.3"
    domain.kind == "extension"
}
