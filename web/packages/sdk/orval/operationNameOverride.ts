// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Example operationIds and their generated names:
// With apis_ prefix (most common):
// - list_jobs_apis_customization_v2_workspaces__workspace__jobs_get              -> customizationListJobs
// - create_job_apis_data_designer_v2_workspaces__workspace__jobs_post         -> dataDesignerCreateJob
// - list_workspaces_apis_entities_v2_workspaces_get                           -> entitiesListWorkspaces
//
// Non-apis_ routes (unchanged):
// - gateway_proxy_get                                                         -> gatewayProxyGet
//
// Pattern: {action}_apis_{service}_{version}_{path}_{method}

/**
 * Converts snake_case string to camelCase
 */
const toCamelCase = (str: string): string =>
  str
    .split('_')
    .map((word, index) =>
      index === 0 ? word.toLowerCase() : word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
    )
    .join('');

/**
 * Singularizes a word using basic English rules.
 * e.g., "entities" -> "entity", "jobs" -> "job", "configs" -> "config"
 */
const singularize = (word: string): string => {
  if (word.endsWith('ies') && word.length > 3) return word.slice(0, -3) + 'y';
  if (word.endsWith('s') && !word.endsWith('ss')) return word.slice(0, -1);
  return word;
};

/**
 * Removes duplicate adjacent words from an array.
 * Also handles singular/plural variations.
 * e.g., ['guardrails', 'chat', 'chat', 'completion'] -> ['guardrails', 'chat', 'completion']
 */
const dedupeAdjacentWords = (words: string[]): string[] => {
  return words.filter((word, index) => {
    if (index === 0) return true;
    const prev = words[index - 1].toLowerCase();
    const curr = word.toLowerCase();
    return prev !== curr && singularize(prev) !== singularize(curr);
  });
};

/**
 * Extracts the primary resource from the path portion of an operationId.
 * Returns the first path segment before any path parameters (marked by __).
 *
 * e.g., "workspaces__workspace__customization_jobs__name__results_get" -> "customization_jobs"
 * e.g., "workspaces_get" -> "workspaces"
 * e.g., "info_get" -> "info"
 */
const extractPrimaryResource = (pathPart: string): string => {
  return extractAllPathResources(pathPart)[0];
};

/**
 * Extracts all resource segments from the path portion of an operationId.
 * Resource segments alternate with path parameter segments (separated by __).
 *
 * e.g., "workspaces__workspace__customization_jobs__name__results_get" -> ["customization_jobs", "results"]
 * e.g., "workspaces__workspace__customization_job_results_get" -> ["customization_job_results"]
 * e.g., "workspaces__workspace__customization_jobs__job__results__name__download_get"
 *        -> ["customization_jobs", "results", "download"]
 */
const extractAllPathResources = (pathPart: string): string[] => {
  // Remove workspace prefix
  const withoutWorkspace = pathPart.replace(/^workspaces__workspace__/, '');

  // Remove HTTP method suffix
  const withoutMethod = withoutWorkspace.replace(/_(get|post|put|patch|delete|head)$/, '');

  // Segments alternate: resource, param, resource, param, ...
  // Even indices (0, 2, 4, ...) are resource segments
  const segments = withoutMethod.split('__');
  return segments.filter((_, i) => i % 2 === 0);
};

/**
 * Qualifies the action resource using path information for disambiguation.
 * When the path is more specific than the action, the path qualifier is prepended.
 *
 * e.g., actionResource="job", pathResource="customization_jobs" -> "customization_job"
 * e.g., actionResource="customization", pathResource="customizations" -> "customization"
 * e.g., actionResource="job_result_artifacts", pathResource="customization_jobs"
 *       -> "customization_job_result_artifacts"
 */
const qualifyResource = (actionResource: string, pathResource: string): string => {
  if (!actionResource || !pathResource) return actionResource;

  const actionWords = actionResource.split('_');
  const pathWords = pathResource.split('_');

  // Singularize the last path word for comparison
  const singPathWords = pathWords.map((w, i) => (i === pathWords.length - 1 ? singularize(w) : w));

  // Find where the first action word appears in the singularized path
  const firstActionSingular = singularize(actionWords[0]);
  const matchIndex = singPathWords.indexOf(firstActionSingular);

  if (matchIndex > 0) {
    // Path has qualifier words before the action resource — prepend them
    const qualifiers = pathWords.slice(0, matchIndex);
    return [...qualifiers, ...actionWords].join('_');
  }

  return actionResource;
};

/**
 * Builds a camelCase operation name from service, verb, and resource parts,
 * deduplicating adjacent words.
 */
const buildOperationName = (service: string, verb: string, resource: string): string => {
  const parts = [service, verb];
  if (resource) {
    parts.push(resource);
  }
  const allWords = parts.join('_').split('_');
  const dedupedWords = dedupeAdjacentWords(allWords);
  return toCamelCase(dedupedWords.join('_'));
};

const normalizeOperationName = (service: string, name: string): string => {
  if (service !== 'intake' || !name.startsWith('intake') || name.length === 'intake'.length) {
    return name;
  }

  const rest = name.slice('intake'.length);
  return rest.charAt(0).toLowerCase() + rest.slice(1);
};

// Track generated names to detect and resolve collisions between endpoints
// that produce the same operation name (e.g., a flat resource endpoint and a
// sub-resource endpoint that qualify to the same name).
const generatedNames = new Set<string>();

/**
 * Extracts the meaningful operation name from FastAPI's auto-generated operationId.
 * Uses the service name as prefix and qualifies resources using path information
 * for disambiguation.
 *
 * @param operation - The operation object containing operationId
 * @returns Unique camelCase operation name (e.g., "customizerCreateJobV2")
 */
export const operationNameOverride = (operation: { operationId?: string }) => {
  const operationId = operation.operationId ?? '';

  // Health endpoints are not versioned — return as-is
  if (operationId.includes('health')) {
    return operationId;
  }

  // Match: {action}_apis_{service}_{version}_{path}_{method}
  const apisMatch = operationId.match(/^(.+?)_apis_(.+?)_(v\d+)_(.+)$/);
  if (!apisMatch) {
    // No apis_ prefix (e.g., gateway_proxy_get) — plain camelCase
    return toCamelCase(operationId);
  }

  const [, actionPart, service, , pathPart] = apisMatch;

  // Split action into verb and resource
  const actionWords = actionPart.split('_');
  const verb = actionWords[0];
  const actionResource = actionWords.slice(1).join('_');

  // Extract the primary resource from path for disambiguation
  const pathResource = extractPrimaryResource(pathPart);

  // Qualify the action resource using path context
  const qualifiedResource = qualifyResource(actionResource, pathResource);

  // Build: {service}_{verb}_{qualifiedResource}
  let name = normalizeOperationName(service, buildOperationName(service, verb, qualifiedResource));

  // If this name was already generated, disambiguate using the full path resources.
  // This handles collisions between flat endpoints (e.g., /metric-job-results) and
  // sub-resource endpoints (e.g., /metric-jobs/{name}/results) that qualify to the
  // same name. Using all path resource segments (with original pluralization)
  // produces a distinct name after dedup, such as "JobResults" vs "JobsResults".
  if (generatedNames.has(name)) {
    const allPathResources = extractAllPathResources(pathPart);
    if (allPathResources.length > 1) {
      const fullPathResource = allPathResources.join('_');
      name = normalizeOperationName(service, buildOperationName(service, verb, fullPathResource));
    }
  }

  generatedNames.add(name);
  return name;
};
