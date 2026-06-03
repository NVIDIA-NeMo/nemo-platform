package authz

import future.keywords.if

import data.authz.extract_path
import data.common.get_domain_metadata

current_domain := domain if {
	path := extract_path
	domain := get_domain_metadata(path)
}
