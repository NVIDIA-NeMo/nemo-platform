// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect } from 'vitest';

import { operationNameOverride } from './operationNameOverride';

describe('operationNameOverride', () => {
  it('creates customization job names', () => {
    expect(
      operationNameOverride({
        operationId: 'create_job_apis_customization_v2_workspaces__workspace__jobs_post',
      })
    ).toBe('customizationCreateJob');
  });

  it('lists customization jobs', () => {
    expect(
      operationNameOverride({
        operationId: 'list_jobs_apis_customization_v2_workspaces__workspace__jobs_get',
      })
    ).toBe('customizationListJobs');
  });

  it('creates data designer job names', () => {
    expect(
      operationNameOverride({
        operationId: 'create_job_apis_data_designer_v2_workspaces__workspace__jobs_post',
      })
    ).toBe('dataDesignerCreateJob');
  });

  it('lists workspaces', () => {
    expect(
      operationNameOverride({
        operationId: 'list_workspaces_apis_entities_v2_workspaces_get',
      })
    ).toBe('entitiesListWorkspaces');
  });

  it('keeps health endpoints unchanged', () => {
    expect(operationNameOverride({ operationId: 'health_health_get' })).toBe('health_health_get');
  });

  it('camel cases non-apis routes', () => {
    expect(operationNameOverride({ operationId: 'gateway_proxy_get' })).toBe('gatewayProxyGet');
  });

  it('keeps flat job result endpoint names', () => {
    expect(
      operationNameOverride({
        operationId: 'list_job_results_apis_audit_v2_workspaces__workspace__job_results_get',
      })
    ).toBe('auditListJobResults');
  });

  it('disambiguates sub-resource job result endpoint names', () => {
    expect(
      operationNameOverride({
        operationId: 'list_job_results_apis_audit_v2_workspaces__workspace__jobs__name__results_get',
      })
    ).toBe('auditListJobsResults');
  });

  it('gets flat job result endpoint names', () => {
    expect(
      operationNameOverride({
        operationId: 'get_job_result_apis_audit_v2_workspaces__workspace__job_results__result__get',
      })
    ).toBe('auditGetJobResult');
  });

  it('disambiguates sub-resource get job result endpoint names', () => {
    expect(
      operationNameOverride({
        operationId: 'get_job_result_apis_audit_v2_workspaces__workspace__jobs__job__results__name__get',
      })
    ).toBe('auditGetJobsResults');
  });

  it('gets audit job logs', () => {
    expect(
      operationNameOverride({
        operationId: 'get_job_logs_apis_audit_v2_workspaces__workspace__jobs__name__logs_get',
      })
    ).toBe('auditGetJobLogs');
  });

  it('drops the redundant intake prefix', () => {
    expect(
      operationNameOverride({
        operationId: 'list_entries_apis_intake_v2_workspaces__workspace__entries_get',
      })
    ).toBe('listEntries');
  });

  it('checks collisions after dropping the intake prefix', () => {
    expect(
      operationNameOverride({
        operationId: 'list_entry_results_apis_intake_v2_workspaces__workspace__entry_results_get',
      })
    ).toBe('listEntryResults');

    expect(
      operationNameOverride({
        operationId: 'list_entry_results_apis_intake_v2_workspaces__workspace__entries__name__results_get',
      })
    ).toBe('listEntriesResults');
  });
});
