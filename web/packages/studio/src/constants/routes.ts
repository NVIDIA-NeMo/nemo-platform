/*
 * SPDX-FileCopyrightText: Copyright (c) 2022-2023 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
 * SPDX-License-Identifier: Apache-2.0
 *
 * NVIDIA CORPORATION, its affiliates and licensors retain all intellectual
 * property and proprietary rights in and to this material, related
 * documentation and any modifications thereto. Any use, reproduction,
 * disclosure or distribution of this material and related documentation
 * without an express license agreement from NVIDIA CORPORATION or
 * its affiliates is strictly prohibited.
 */

export const ROUTE_PARAMS = {
  completionId: 'completionId',
  evaluationJobId: 'id',
  customizationJobId: 'customizationJobId',
  customizationJobName: 'customizationJobName',
  filesetId: 'filesetId',
  filesetName: 'filesetName',
  filePathEncoded: 'filePathEncoded',
  folderPathEncoded: 'folderPathEncoded',
  workspace: 'workspace',
  modelNamespace: 'modelNamespace',
  modelName: 'modelName',
  evalConfigNamespace: 'configNamespace',
  evalConfigName: 'configName',
  safeSynthesizerJobName: 'safeSynthesizerJobName',
  dataDesignerJobName: 'dataDesignerJobName',
  traceId: 'traceId',
  spanId: 'spanId',
  deploymentConfigName: 'deploymentConfigName',
  deploymentName: 'deploymentName',
  /** Side panel mode under deployments (e.g. `details`). */
  deploymentPanelView: 'deploymentPanelView',
  agentName: 'agentName',
  agentDeploymentName: 'agentDeploymentName',
  agentEvalJobName: 'agentEvalJobName',
  jobName: 'jobName',
  /** Benchmark entity name segment under evaluation/benchmarks/:name */
  benchmarkName: 'benchmarkName',
  experimentGroupName: 'experimentGroupName',
  experimentName: 'experimentName',
} as const;

// Just an alias to make the routes more readable
const P = ROUTE_PARAMS;

export const ROUTES = {
  auth: {
    success: '/auth/success',
  },
  workspace: {
    /**  Just redirects to the workspace dashboard route */
    index: `/workspaces/:${P.workspace}`,
    dashboard: `/workspaces/:${P.workspace}/dashboard`,
    jobs: `/workspaces/:${P.workspace}/jobs`,
    jobDetail: `/workspaces/:${P.workspace}/jobs/:${P.jobName}`,
    promptTuningForm: `/workspaces/:${P.workspace}/customizations/prompt-tuned/new`,
    baseModels: `/workspaces/:${P.workspace}/base-models`,
    /** Base models list with a specific model panel open (model name in path) */
    baseModelsModel: `/workspaces/:${P.workspace}/base-models/:${P.modelName}`,
    evaluation: `/workspaces/:${P.workspace}/evaluation`,
    evaluationMetrics: `/workspaces/:${P.workspace}/evaluation/metrics`,
    evaluationMetricNew: `/workspaces/:${P.workspace}/evaluation/metrics/new`,
    /** Run panel without a pre-selected metric — user picks from within the panel */
    evaluationMetricsRun: `/workspaces/:${P.workspace}/evaluation/metrics/run`,
    evaluationMetricDetails: `/workspaces/:${P.workspace}/evaluation/metrics/:${P.evaluationJobId}`,
    evaluationMetricRun: `/workspaces/:${P.workspace}/evaluation/metrics/:${P.evaluationJobId}/run`,
    evaluationBenchmarks: `/workspaces/:${P.workspace}/evaluation/benchmarks`,
    evaluationBenchmarkDetails: `/workspaces/:${P.workspace}/evaluation/benchmarks/:${P.benchmarkName}`,
    evaluationResults: `/workspaces/:${P.workspace}/evaluation/results`,
    evaluationResultDetails: `/workspaces/:${P.workspace}/evaluation/results/:${P.evaluationJobId}`,
    /** Empty landing page for the EXPERIMENT feature (gated by VITE_FF_EXPERIMENT). */
    experiment: `/workspaces/:${P.workspace}/experiment`,
    experimentGroupDetail: `/workspaces/:${P.workspace}/experiment/:${P.experimentGroupName}`,
    experimentDetail: `/workspaces/:${P.workspace}/experiment/:${P.experimentGroupName}/:${P.experimentName}`,
    customizationJobList: `/workspaces/:${P.workspace}/customizations`,
    customizationJobDetails: `/workspaces/:${P.workspace}/customizations/:${P.customizationJobName}`,
    newCustomizationJob: `/workspaces/:${P.workspace}/customizations/fine-tuned/new`,
    filesets: `/workspaces/:${P.workspace}/filesets`,
    filesetNew: `/workspaces/:${P.workspace}/filesets/new`,
    filesetDetails: `/workspaces/:${P.workspace}/filesets/:${P.filesetId}`,
    filesetFile: `/workspaces/:${P.workspace}/filesets/:${P.filesetId}/file/:${P.filePathEncoded}`,
    /**
     * Unified fileset detail page (gated by VITE_FF_FILESET_DETAILS_ENABLED).
     * One route serves all purposes — the page branches on `fileset.purpose`
     * to render Model/Dataset/Generic card content.
     */
    filesetDetail: `/workspaces/:${P.workspace}/filesets/:${P.filesetName}/detail`,
    inferenceProviders: `/workspaces/:${P.workspace}/inference-providers`,
    deploymentConfigs: `/workspaces/:${P.workspace}/deployment-configs`,
    deployments: `/workspaces/:${P.workspace}/deployments`,
    /** Deployments list with details side panel (deployment name + panel segment, e.g. `details`). */
    deploymentsDeployment: `/workspaces/:${P.workspace}/deployments/:${P.deploymentName}/:${P.deploymentPanelView}`,
    intake: `/workspaces/:${P.workspace}/intake`,
    intakeTraces: `/workspaces/:${P.workspace}/intake/traces`,
    intakeSpans: `/workspaces/:${P.workspace}/intake/spans`,
    intakeTrace: `/workspaces/:${P.workspace}/intake/traces/:${P.traceId}`,
    intakeSpan: `/workspaces/:${P.workspace}/intake/spans/:${P.spanId}`,
    safeSynthesizer: `/workspaces/:${P.workspace}/safe-synthesizer`,
    safeSynthesizerNew: `/workspaces/:${P.workspace}/safe-synthesizer/new`,
    safeSynthesizerJob: `/workspaces/:${P.workspace}/safe-synthesizer/job/:${P.safeSynthesizerJobName}`,
    safeSynthesizerJobReport: `/workspaces/:${P.workspace}/safe-synthesizer/job/:${P.safeSynthesizerJobName}/report`,
    dataDesignerJobList: `/workspaces/:${P.workspace}/data-designer`,
    dataDesignerJobDetails: `/workspaces/:${P.workspace}/data-designer/:${P.dataDesignerJobName}`,
    dataDesignerJobNew: `/workspaces/:${P.workspace}/data-designer/new`,
    secrets: `/workspaces/:${P.workspace}/secrets`,
    guardrails: `/workspaces/:${P.workspace}/guardrails`,
    settings: `/workspaces/:${P.workspace}/settings`,
    /** Workspace members and role-based access (Entities role bindings) */
    members: `/workspaces/:${P.workspace}/members`,
    agentsList: `/workspaces/:${P.workspace}/agents`,
    claudeCodeChat: `/workspaces/:${P.workspace}/dashboard/code-agent`,
    agentDetail: `/workspaces/:${P.workspace}/agents/:${P.agentName}`,
    agentDeploymentsList: `/workspaces/:${P.workspace}/agent-deployments`,
    agentDeploymentDetail: `/workspaces/:${P.workspace}/agent-deployments/:${P.agentDeploymentName}`,
    /** Agent-evaluation jobs list (Phase 2 of the agent-eval UX). */
    agentEvaluationsList: `/workspaces/:${P.workspace}/agents/evaluations`,
    /** Detail view for a single agent-evaluation job. */
    agentEvaluationDetail: `/workspaces/:${P.workspace}/agents/evaluations/:${P.agentEvalJobName}`,
    modelCompare: `/workspaces/:${P.workspace}/model-compare`,
    agentOptimizations: `/workspaces/:${P.workspace}/agents/suggestions`,
    agentMonitor: `/workspaces/:${P.workspace}/agents/monitor`,
  },
  models: {
    index: '/models',
    modelChat: `/models/:${P.modelNamespace}/:${P.modelName}/chat`,
  },
} as const;
