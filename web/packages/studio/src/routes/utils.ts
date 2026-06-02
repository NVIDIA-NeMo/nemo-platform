// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { getPartsFromNamedEntityRef, NamedEntityRef } from '@nemo/common/src/namedEntity';
import {
  AGENTS_ENABLED,
  BASE_MODELS_ENABLED,
  CUSTOMIZER_ENABLED,
  DASHBOARD_ENABLED,
  DATA_DESIGNER_ENABLED,
  DATASETS_ENABLED,
  DEPLOYMENTS_ENABLED,
  EVALUATOR_BENCHMARKS_ENABLED,
  EVALUATOR_ENABLED,
  FILESET_DETAILS_ENABLED,
  GUARDRAILS_ENABLED,
  INFERENCE_PROVIDER_ENABLED,
  INTAKE_ENABLED,
  JOBS_ENABLED,
  MEMBERS_ENABLED,
  MODEL_COMPARE_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
  SECRETS_ENABLED,
  SETTINGS_ENABLED,
} from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { QUERY_PARAMETERS } from '@studio/routes/constants';
import { DatasetDetailTab } from '@studio/routes/DatasetDetailRoute/constants';
import { ModelDetailTab } from '@studio/routes/ModelDetailRoute/constants';
import { generatePath, RouteObject } from 'react-router';

const gateRoutes = (enabled: boolean, routes: RouteObject | RouteObject[]) => {
  if (!enabled) return [];
  return Array.isArray(routes) ? routes : [routes];
};

export const gateBaseModelsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(BASE_MODELS_ENABLED, routes);

export const gateCustomizationRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(CUSTOMIZER_ENABLED, routes);

export const gateDashboardRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(DASHBOARD_ENABLED, routes);

export const gateDatasetsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(DATASETS_ENABLED, routes);

export const gateFilesetDetailsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(FILESET_DETAILS_ENABLED, routes);

export const gateJobsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(JOBS_ENABLED, routes);

export const gateSettingsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(SETTINGS_ENABLED, routes);

export const gateIntakeRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(INTAKE_ENABLED, routes);

export const gateSafeSynthesizerRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(SAFE_SYNTHESIZER_ENABLED, routes);

export const gateDataDesignerRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(DATA_DESIGNER_ENABLED, routes);

export const gateEvaluationRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(EVALUATOR_ENABLED, routes);

export const gateEvaluationBenchmarksRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(EVALUATOR_ENABLED && EVALUATOR_BENCHMARKS_ENABLED, routes);

export const gateSecretsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(SECRETS_ENABLED, routes);

export const gateGuardrailsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(GUARDRAILS_ENABLED, routes);

export const gateInferenceProviderRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(INFERENCE_PROVIDER_ENABLED, routes);

export const gateMembersRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(MEMBERS_ENABLED, routes);

export const agentsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(AGENTS_ENABLED, routes);

export const gateDeploymentsRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(DEPLOYMENTS_ENABLED, routes);

export const gateModelCompareRoutes = (routes: RouteObject | RouteObject[]) =>
  gateRoutes(MODEL_COMPARE_ENABLED, routes);

type WorkspacePathParams = {
  workspace: string;
};

type ModelRouteParams = {
  modelNamespace: string;
  modelName: string;
};

const getModelRouteParamsFromEntityRef = (model: NamedEntityRef): ModelRouteParams => {
  const { workspace, name } = getPartsFromNamedEntityRef(model);
  return { modelNamespace: workspace, modelName: name };
};

export const getCustomizationJobListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.customizationJobList, { workspace });
};

export const getNewCustomizationJobRoute = (workspace: string, options?: { model?: string }) => {
  const basePath = generatePath(ROUTES.workspace.newCustomizationJob, { workspace });
  if (options?.model) {
    return `${basePath}?model=${encodeURIComponent(options.model)}`;
  }
  return basePath;
};

export const getWorkspacePathParamsFromName = (workspace: string): WorkspacePathParams => {
  return { workspace };
};

export const getWorkspaceIndexRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.index, { workspace });
};

export const getWorkspaceDetailsDefaultRoute = (workspace: string) => {
  if (DASHBOARD_ENABLED) return getWorkspaceDashboardRoute(workspace);
  if (AGENTS_ENABLED) return getAgentsListRoute(workspace);
  if (BASE_MODELS_ENABLED) return getWorkspaceBaseModelsRoute(workspace);
  if (JOBS_ENABLED) return getWorkspaceJobsRoute(workspace);
  return getWorkspaceIndexRoute(workspace);
};

export const getWorkspaceDashboardRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.dashboard, { workspace });
};

export const getWorkspaceJobsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.jobs, { workspace });
};

export const getWorkspaceJobDetailRoute = (workspace: string, jobName: string) => {
  return generatePath(ROUTES.workspace.jobDetail, { workspace, jobName });
};

export type BaseModelsPanelTab = 'model-details' | 'chat-playground';

export const getWorkspaceBaseModelsRoute = (
  workspace: string,
  options?: { model?: string; tab?: BaseModelsPanelTab; searchParams?: URLSearchParams }
): string => {
  let path: string;
  const searchParams = new URLSearchParams(options?.searchParams);
  if (options?.model) {
    path = generatePath(ROUTES.workspace.baseModelsModel, {
      workspace,
      modelName: encodeURIComponent(options.model),
    });
    if (options?.tab) {
      searchParams.set('tab', options.tab);
    }
  } else {
    path = generatePath(ROUTES.workspace.baseModels, { workspace });
  }

  const query = searchParams.toString();
  return query ? `${path}?${query}` : path;
};

export const getWorkspaceFilesetsRoute = (workspace: string) => {
  const searchParams = new URLSearchParams(window.location.search);
  const baseUrl = generatePath(ROUTES.workspace.filesets, { workspace });

  return searchParams.size ? `${baseUrl}?${searchParams.toString()}` : baseUrl;
};

export const getWorkspaceCustomizationJobDetailsRoute = (
  workspace: string,
  customizationJobName: string
) => {
  return generatePath(ROUTES.workspace.customizationJobDetails, {
    workspace,
    customizationJobName,
  });
};

export const getWorkspaceCustomizationJobListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.customizationJobList, { workspace });
};

export const getWorkspaceNewCustomizationJobRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.newCustomizationJob, { workspace });
};

export const getWorkspaceEvaluationRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.evaluation, { workspace });
};

export const getWorkspaceInferenceProvidersRoute = (
  workspace: string,
  options?: { preset?: string }
): string => {
  const base = generatePath(ROUTES.workspace.inferenceProviders, { workspace });
  if (options?.preset) {
    return `${base}?create=true&preset=${encodeURIComponent(options.preset)}`;
  }
  return base;
};

export const getWorkspaceDeploymentsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.deployments, { workspace });
};

/** Default segment for the deployment details side panel URL. */
export const DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS = 'details' as const;

export const getWorkspaceDeploymentDetailsRoute = (
  workspace: string,
  deploymentName: string,
  panelView: string = DEPLOYMENT_DETAILS_PANEL_VIEW_DETAILS
) => {
  return generatePath(ROUTES.workspace.deploymentsDeployment, {
    workspace,
    deploymentName: encodeURIComponent(deploymentName),
    deploymentPanelView: panelView,
  });
};

export const getWorkspaceSafeSynthesizerRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.safeSynthesizer, { workspace });
};

export const getEvaluationRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.evaluation, { workspace });
};

export const getEvaluationMetricsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.evaluationMetrics, { workspace });
};

export const getNewEvaluationMetricRoute = (workspace: string, options?: { model?: string }) => {
  const searchParams = new URLSearchParams();
  if (options?.model) {
    searchParams.append('model', options.model);
  }
  const baseUrl = generatePath(ROUTES.workspace.evaluationMetricNew, {
    workspace,
  });
  return searchParams.size ? `${baseUrl}?${searchParams.toString()}` : baseUrl;
};

export const getEvaluationMetricDetailsRoute = (workspace: string, metricId: string) => {
  return generatePath(ROUTES.workspace.evaluationMetricDetails, {
    workspace,
    id: metricId,
  });
};

/** Run panel without a pre-selected metric (user picks from within the panel). */
export const getEvaluationMetricsRunRoute = (workspace: string, options?: { model?: string }) => {
  const basePath = generatePath(ROUTES.workspace.evaluationMetricsRun, { workspace });
  if (options?.model) {
    return `${basePath}?${QUERY_PARAMETERS.model}=${encodeURIComponent(options.model)}`;
  }
  return generatePath(ROUTES.workspace.evaluationMetricsRun, { workspace });
};

/** Run panel pre-populated for a specific metric. */
export const getEvaluationMetricRunRoute = (
  workspace: string,
  metricId: string,
  options?: { model?: string }
) => {
  const basePath = generatePath(ROUTES.workspace.evaluationMetricRun, { workspace, id: metricId });
  if (options?.model) {
    return `${basePath}?${QUERY_PARAMETERS.model}=${encodeURIComponent(options.model)}`;
  }
  return basePath;
};

export const getEvaluationBenchmarkListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.evaluationBenchmarks, { workspace });
};

export const getEvaluationBenchmarkDetailsRoute = (workspace: string, benchmarkName: string) => {
  return generatePath(ROUTES.workspace.evaluationBenchmarkDetails, {
    workspace,
    benchmarkName,
  });
};

export const getEvaluationResultsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.evaluationResults, { workspace });
};

export const getEvaluationResultDetailsRoute = (workspace: string, jobName: string) => {
  return generatePath(ROUTES.workspace.evaluationResultDetails, {
    workspace,
    id: jobName,
  });
};

export const getPromptTuningFormRoute = (workspace: string, options?: { model?: string }) => {
  const basePath = generatePath(ROUTES.workspace.promptTuningForm, { workspace });
  if (options?.model) {
    return `${basePath}?model=${encodeURIComponent(options.model)}`;
  }
  return basePath;
};

export const getNewFilesetRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.filesetNew, { workspace });
};

export const getSecretsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.secrets, { workspace });
};

export const getGuardrailsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.guardrails, { workspace });
};

export const getWorkspaceSettingsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.settings, { workspace });
};

export const getWorkspaceMembersRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.members, { workspace });
};

export const getModelCompareRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.modelCompare, { workspace });
};

export const getFilesetDetailsRoute = (
  workspace: string,
  filesetId: string,
  filesetFolder?: string,
  resetPage?: boolean
) => {
  const searchParams = new URLSearchParams(window.location.search);
  if (filesetFolder) {
    searchParams.set(QUERY_PARAMETERS.filesetFolder, filesetFolder);
  } else {
    searchParams.delete(QUERY_PARAMETERS.filesetFolder);
  }
  const baseUrl = generatePath(ROUTES.workspace.filesetDetails, {
    workspace,
    filesetId,
  });

  if (resetPage) {
    // To make sure the new fileset is front and center we need to remove some query params
    // If we are OK not showing the current fileset in the table this could be removed
    searchParams.delete('page');
    searchParams.delete('sort_by');
    searchParams.delete('order');
  }

  return searchParams.size ? `${baseUrl}?${searchParams.toString()}` : baseUrl;
};

export const getDatasetDetailRoute = (
  workspace: string,
  datasetName: string,
  options?: { tab?: DatasetDetailTab }
) => {
  const base = generatePath(ROUTES.workspace.datasetDetail, { workspace, datasetName });
  return options?.tab ? `${base}?${QUERY_PARAMETERS.tab}=${options.tab}` : base;
};

export const getModelDetailRoute = (
  workspace: string,
  modelName: string,
  options?: { tab?: ModelDetailTab }
) => {
  const base = generatePath(ROUTES.workspace.modelDetail, { workspace, modelName });
  return options?.tab ? `${base}?${QUERY_PARAMETERS.tab}=${options.tab}` : base;
};

export const getFilesetFileRoute = (workspace: string, fileset: string, filePath: string) => {
  return generatePath(ROUTES.workspace.filesetFile, {
    workspace,
    filesetId: encodeURIComponent(fileset),
    filePathEncoded: encodeURIComponent(filePath),
  });
};

export const getIntakeRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.intake, { workspace });
};

export const getIntakeTracesRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.intakeTraces, { workspace });
};

export const getIntakeSpansRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.intakeSpans, { workspace });
};

export const getIntakeTraceRoute = (workspace: string, traceId: string) => {
  return generatePath(ROUTES.workspace.intakeTrace, { workspace, traceId });
};

export const getIntakeSpanRoute = (workspace: string, spanId: string) => {
  return generatePath(ROUTES.workspace.intakeSpan, { workspace, spanId });
};

export const getSafeSynthesizerRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.safeSynthesizer, { workspace });
};

export const getNewSafeSynthesizerRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.safeSynthesizerNew, { workspace });
};

export const getSafeSynthesizerJobRoute = (workspace: string, safeSynthesizerJobName: string) => {
  return generatePath(ROUTES.workspace.safeSynthesizerJob, {
    workspace,
    safeSynthesizerJobName,
  });
};

export const getSafeSynthesizerJobReportRoute = (
  workspace: string,
  safeSynthesizerJobName: string
) => {
  return generatePath(ROUTES.workspace.safeSynthesizerJobReport, {
    workspace,
    safeSynthesizerJobName,
  });
};

export const getDataDesignerJobListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.dataDesignerJobList, { workspace });
};

export const getDataDesignerJobDetailsRoute = (workspace: string, dataDesignerJobName: string) => {
  return generatePath(ROUTES.workspace.dataDesignerJobDetails, {
    workspace,
    dataDesignerJobName,
  });
};

export const getNewDataDesignerJobRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.dataDesignerJobNew, { workspace });
};

export const getModelChatRoute = (model: NamedEntityRef) => {
  const { modelNamespace, modelName } = getModelRouteParamsFromEntityRef(model);
  return generatePath(ROUTES.models.modelChat, { modelNamespace, modelName });
};

export const getAgentsListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.agentsList, { workspace });
};

export const getAgentDetailRoute = (workspace: string, agentName: string) => {
  return generatePath(ROUTES.workspace.agentDetail, { workspace, agentName });
};

export const getAgentDeploymentsListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.agentDeploymentsList, { workspace });
};

export const getAgentDeploymentDetailRoute = (workspace: string, agentDeploymentName: string) => {
  return generatePath(ROUTES.workspace.agentDeploymentDetail, {
    workspace,
    agentDeploymentName,
  });
};

export const getAgentOptimizationsRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.agentOptimizations, { workspace });
};

export const getAgentMonitorRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.agentMonitor, { workspace });
};

export const getAgentEvaluationsListRoute = (workspace: string) => {
  return generatePath(ROUTES.workspace.agentEvaluationsList, { workspace });
};

export const getAgentEvaluationDetailRoute = (workspace: string, agentEvalJobName: string) => {
  return generatePath(ROUTES.workspace.agentEvaluationDetail, {
    workspace,
    agentEvalJobName,
  });
};
