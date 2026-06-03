package authz

import future.keywords.if

import data.authz.extract_path
import data.common.get_domain_metadata

current_domain := domain if {
	path := extract_path
	domain := get_domain_metadata(path)
}

has_domain_policy(domain_name) if {
	data.authz.domain_policies[domain_name]
}

default domain_policy_checks_pass := false

domain_policy_checks_pass if {
	not current_domain
}

domain_policy_checks_pass if {
	current_domain
	not has_domain_policy(current_domain.name)
}

domain_policy_checks_pass if {
	domain := current_domain
	has_domain_policy(domain.name)
	policy := data.authz.domain_policies[domain.name]
	# First cut: policy presence activates the domain layer without
	# adding additional deny conditions yet.
	policy
}
