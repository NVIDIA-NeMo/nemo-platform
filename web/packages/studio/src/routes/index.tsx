// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ErrorMessage } from '@nemo/common/src/components/ErrorMessage';
import { Stack } from '@nvidia/foundations-react-core';
import { ErrorPanel } from '@studio/components/ErrorPanel';
import { Loading } from '@studio/components/Layouts/Loading';
import {
  AGENTS_ENABLED,
  CODING_AGENT_STUDIO_ENABLED,
  DATA_DESIGNER_ENABLED,
  DEPLOYMENTS_ENABLED,
  GUARDRAILS_ENABLED,
  MODEL_COMPARE_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
} from '@studio/constants/environment';
import { ROUTES } from '@studio/constants/routes';
import { INTAKE_FILTER_ACTION_TARGET_ID } from '@studio/routes/IntakeLayout';
import { PageLayout } from '@studio/routes/PageLayout';
import { RootLayout } from '@studio/routes/RootLayout';
import { RootRedirect } from '@studio/routes/RootRedirect';
import {
  agentsRoutes,
  gateBaseModelsRoutes,
  gateCodingAgentStudioRoutes,
  gateCustomizationRoutes,
  gateDatasetsRoutes,
  gateDeploymentsRoutes,
  gateDataDesignerRoutes,
  gateEvaluationBenchmarksRoutes,
  gateEvaluationRoutes,
  gateFilesetDetailsRoutes,
  gateGuardrailsRoutes,
  gateInferenceProviderRoutes,
  gateIntakeRoutes,
  gateJobsRoutes,
  gateMembersRoutes,
  gateSafeSynthesizerRoutes,
  gateModelCompareRoutes,
  gateSecretsRoutes,
  gateSettingsRoutes,
  gateDashboardRoutes,
} from '@studio/routes/utils';
import { FC, lazy, Suspense } from 'react';
import { Outlet } from 'react-router';
import { Navigate, RouteObject } from 'react-router-dom';

const IntakeLayout = lazy(() =>
  import('@studio/routes/IntakeLayout').then((module) => ({ default: module.IntakeLayout }))
);
const IntakeTracesTableRoute = lazy(() =>
  import('@studio/components/IntakeTracesTable').then(({ IntakeTracesTable }) => {
    const IntakeTracesTableRouteComponent: FC = () => (
      <Stack className="flex-1 min-h-0">
        <IntakeTracesTable filterTogglePortalTargetId={INTAKE_FILTER_ACTION_TARGET_ID} />
      </Stack>
    );

    return { default: IntakeTracesTableRouteComponent };
  })
);
const IntakeSpansTableRoute = lazy(() =>
  import('@studio/components/IntakeSpansTable').then(({ IntakeSpansTable }) => {
    const IntakeSpansTableRouteComponent: FC = () => (
      <Stack className="flex-1 min-h-0">
        <IntakeSpansTable filterTogglePortalTargetId={INTAKE_FILTER_ACTION_TARGET_ID} />
      </Stack>
    );

    return { default: IntakeSpansTableRouteComponent };
  })
);
const IntakeTraceDetailRoute = lazy(() =>
  import('@studio/routes/IntakeTraceDetailRoute').then((module) => ({
    default: module.IntakeTraceDetailRoute,
  }))
);
const IntakeSpanDetailRoute = lazy(() =>
  import('@studio/routes/IntakeSpanDetailRoute').then((module) => ({
    default: module.IntakeSpanDetailRoute,
  }))
);
const CustomizationJobDetailsRoute = lazy(() =>
  import('@studio/routes/CustomizationJobDetailsRoute').then((module) => ({
    default: module.CustomizationJobDetailsRoute,
  }))
);
const CustomizationJobListRoute = lazy(() =>
  import('@studio/routes/CustomizationJobListRoute').then((module) => ({
    default: module.CustomizationJobListRoute,
  }))
);
const FilesetNewRoute = lazy(() =>
  import('@studio/routes/FilesetNewRoute').then((module) => ({ default: module.FilesetNewRoute }))
);
// Fileset details and file routes are not separate routes
// Both panels are rendered directly in FilesetListRoute
// Route paths are kept for URL matching only
const FilesetListRoute = lazy(() =>
  import('@studio/routes/FilesetListRoute').then((module) => ({ default: module.FilesetListRoute }))
);
const DatasetDetailRoute = lazy(() =>
  import('@studio/routes/DatasetDetailRoute').then((module) => ({
    default: module.DatasetDetailRoute,
  }))
);
const ModelDetailRoute = lazy(() =>
  import('@studio/routes/ModelDetailRoute').then((module) => ({
    default: module.ModelDetailRoute,
  }))
);
const SecretsListRoute = lazy(() =>
  import('@studio/routes/SecretsListRoute').then((module) => ({ default: module.SecretsListRoute }))
);
const InferenceProvidersListRoute = lazy(() =>
  import('@studio/routes/InferenceProvidersListRoute').then((module) => ({
    default: module.InferenceProvidersListRoute,
  }))
);
const DeploymentsListRoute =
  DEPLOYMENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/DeploymentsListRoute').then((module) => ({
      default: module.DeploymentsListRoute,
    }))
  );
const EvaluationMetricsRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationMetricsRoute').then((module) => ({
    default: module.EvaluationMetricsRoute,
  }))
);
const EvaluationBenchmarksRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationBenchmarksRoute').then((module) => ({
    default: module.EvaluationBenchmarksRoute,
  }))
);
const EvaluationLayout = lazy(() =>
  import('@studio/routes/evaluation/EvaluationLayout').then((module) => ({
    default: module.EvaluationLayout,
  }))
);
const EvaluationResultsLayout = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultsLayout').then((module) => ({
    default: module.EvaluationResultsLayout,
  }))
);
const EvaluationResultsRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultsRoute').then((module) => ({
    default: module.EvaluationResultsRoute,
  }))
);
const NewCustomizationRoute = lazy(() =>
  import('@studio/routes/NewCustomizationRoute').then((module) => ({
    default: module.NewCustomizationRoute,
  }))
);
const NewEvaluationMetricRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationMetricCreateRoute').then((module) => ({
    default: module.EvaluationMetricCreateRoute,
  }))
);
const EvaluationResultDetailsRoute = lazy(() =>
  import('@studio/routes/evaluation/EvaluationResultDetailsRoute').then((module) => ({
    default: module.EvaluationResultDetailsRoute,
  }))
);
const NoMatchRoute = lazy(() =>
  import('@studio/routes/NoMatchRoute').then((module) => ({ default: module.NoMatchRoute }))
);
const PromptTuningFormRoute = lazy(() =>
  import('@studio/routes/PromptTuningFormRoute/index').then((module) => ({
    default: module.PromptTuningFormRoute,
  }))
);
const DashboardLandingRoute = lazy(() =>
  import('@studio/routes/DashboardLandingRoute').then((module) => ({
    default: module.DashboardLandingRoute,
  }))
);
const ModelCompareRoute =
  MODEL_COMPARE_ENABLED &&
  lazy(() =>
    import('@studio/routes/ModelCompareRoute').then((module) => ({
      default: module.ModelCompareRoute,
    }))
  );
/*const ProjectDashboardRoute = lazy(() =>
  import('@studio/routes/ProjectDashboardRoute').then((module) => ({
    default: module.ProjectDashboardRoute,
  }))
);
const ProjectIndexRoute = lazy(() =>
  import('@studio/routes/ProjectIndexRoute').then((module) => ({ default: module.ProjectIndexRoute }))
);
const ProjectSideNav = lazy(() =>
  import('@studio/routes/ProjectLayout/ProjectSideNav').then((module) => ({
    default: module.ProjectSideNav,
  }))
);
const ProjectListLayout = lazy(() =>
  import('@studio/routes/ProjectListLayout').then((module) => ({ default: module.ProjectListLayout }))
);
const ProjectListRoute = lazy(() =>
  import('@studio/routes/ProjectListRoute').then((module) => ({ default: module.ProjectListRoute }))
);*/

// Workspace routes
const WorkspaceDashboardRoute = lazy(() =>
  import('@studio/routes/WorkspaceDashboardRoute').then((module) => ({
    default: module.WorkspaceDashboardRoute,
  }))
);
const JobsRoute = lazy(() =>
  import('@studio/routes/JobsRoute').then((module) => ({
    default: module.JobsRoute,
  }))
);
const JobDetailRoute = lazy(() =>
  import('@studio/routes/JobDetailRoute').then((module) => ({
    default: module.JobDetailRoute,
  }))
);
const WorkspaceBaseModelsRoute = lazy(() =>
  import('@studio/routes/WorkspaceBaseModelsRoute').then((module) => ({
    default: module.WorkspaceBaseModelsRoute,
  }))
);
const WorkspaceIndexRoute = lazy(() =>
  import('@studio/routes/WorkspaceIndexRoute').then((module) => ({
    default: module.WorkspaceIndexRoute,
  }))
);
const WorkspaceSideNav = lazy(() =>
  import('@studio/routes/WorkspaceLayout/WorkspaceSideNav').then((module) => ({
    default: module.WorkspaceSideNav,
  }))
);
const WorkspaceSettingsRoute = lazy(() =>
  import('@studio/routes/WorkspaceSettingsRoute').then((module) => ({
    default: module.WorkspaceSettingsRoute,
  }))
);
const WorkspaceMembersRoute = lazy(() =>
  import('@studio/routes/WorkspaceMembersRoute').then((module) => ({
    default: module.WorkspaceMembersRoute,
  }))
);

const AuthSuccessRoute = lazy(() =>
  import('@studio/routes/AuthSuccessRoute').then((m) => ({
    default: m.AuthSuccessRoute,
  }))
);

const SafeSynthesizerListRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerListRoute').then((m) => ({
      default: m.SafeSynthesizerListRoute as FC,
    }))
  );
const SafeSynthesizerNewRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerNewRoute').then((m) => ({
      default: m.SafeSynthesizerNewRoute as FC,
    }))
  );

const SafeSynthesizerJobDetailsRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerJobDetailsRoute').then((m) => ({
      default: m.SafeSynthesizerJobDetailsRoute as FC,
    }))
  );

const SafeSynthesizerJobReportRoute =
  SAFE_SYNTHESIZER_ENABLED &&
  lazy(() =>
    import('@studio/routes/SafeSynthesizerJobReportRoute').then((m) => ({
      default: m.SafeSynthesizerJobReportRoute as FC,
    }))
  );

const DataDesignerJobListRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/DataDesignerJobListRoute').then((m) => ({
      default: m.DataDesignerJobListRoute,
    }))
  );
const DataDesignerJobDetailsRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/DataDesignerJobDetailsRoute').then((m) => ({
      default: m.DataDesignerJobDetailsRoute,
    }))
  );
const NewDataDesignerJobRoute =
  DATA_DESIGNER_ENABLED &&
  lazy(() =>
    import('@studio/routes/NewDataDesignerJobRoute').then((m) => ({
      default: m.NewDataDesignerJobRoute,
    }))
  );
const AgentsListRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentsListRoute').then((m) => ({
      default: m.AgentsListRoute,
    }))
  );
const ClaudeCodeChatRoute = lazy(() =>
  import('@studio/routes/agents/ClaudeCodeChatRoute').then((m) => ({
    default: m.ClaudeCodeChatRoute,
  }))
);
const AgentOptimizationsRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentSuggestionsRoute').then((m) => ({
      default: m.AgentOptimizationsRoute,
    }))
  );
const AgentMonitorRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentMonitorRoute').then((m) => ({
      default: m.AgentMonitorRoute,
    }))
  );
const AgentEvaluationsListRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentEvaluationsRoute').then((m) => ({
      default: m.AgentEvaluationsListRoute,
    }))
  );
const AgentEvaluationDetailRoute =
  AGENTS_ENABLED &&
  lazy(() =>
    import('@studio/routes/agents/AgentEvaluationsRoute').then((m) => ({
      default: m.AgentEvaluationDetailRoute,
    }))
  );

const GuardrailsRoute =
  GUARDRAILS_ENABLED &&
  lazy(() =>
    import('@studio/routes/guardrails/GuardrailsRoute').then((m) => ({
      default: m.GuardrailsRoute,
    }))
  );

export const routes: RouteObject[] = [
  {
    path: '/health',
    element: <>OK</>,
  },
  {
    element: <RootLayout />,
    errorElement: <ErrorMessage height="100vh" />,
    children: [
      {
        path: ROUTES.auth.success,
        element: <AuthSuccessRoute />,
      },
      {
        element: <PageLayout />,
        children: [
          {
            path: '/',
            element: <RootRedirect />,
          },
          {
            path: '/workspaces',
            element: <RootRedirect />,
          },
          {
            path: '*',
            element: <NoMatchRoute />,
          },
        ],
      },
      {
        path: ROUTES.workspace.index,
        element: <PageLayout sideNav={(collapsed) => <WorkspaceSideNav collapsed={collapsed} />} />,
        children: [
          {
            path: ROUTES.workspace.index,
            element: <WorkspaceIndexRoute />,
          },
          {
            element: (
              // Suspense queries will show loader in panel area
              <Suspense fallback={<Loading description="Loading..." />}>
                <Outlet />
              </Suspense>
            ),
            errorElement: <ErrorPanel title="Entity Store" />,
            children: [
              ...gateDashboardRoutes([
                {
                  path: ROUTES.workspace.dashboard,
                  element: CODING_AGENT_STUDIO_ENABLED ? (
                    <Suspense fallback={<Loading description="Loading Dashboard..." />}>
                      <DashboardLandingRoute />
                    </Suspense>
                  ) : (
                    <WorkspaceDashboardRoute />
                  ),
                  errorElement: <ErrorPanel title="Workspace" />,
                },
                ...gateCodingAgentStudioRoutes([
                  {
                    path: ROUTES.workspace.claudeCodeChat,
                    element: (
                      <Suspense fallback={<Loading description="Loading..." />}>
                        <ClaudeCodeChatRoute />
                      </Suspense>
                    ),
                    errorElement: <ErrorPanel title="Claude Code" />,
                  },
                ]),
              ]),
              ...gateBaseModelsRoutes([
                {
                  path: ROUTES.workspace.baseModels,
                  element: (
                    <Suspense fallback={<Loading description="Loading Base Models..." />}>
                      <WorkspaceBaseModelsRoute />
                    </Suspense>
                  ),
                },
                {
                  path: ROUTES.workspace.baseModelsModel,
                  element: (
                    <Suspense fallback={<Loading description="Loading Base Models..." />}>
                      <WorkspaceBaseModelsRoute />
                    </Suspense>
                  ),
                },
              ]),
              ...gateDatasetsRoutes([
                {
                  path: ROUTES.workspace.filesets,
                  element: <FilesetListRoute />,
                  errorElement: <ErrorPanel title="Filesets" />,
                  children: [
                    {
                      path: ROUTES.workspace.filesetNew,
                      element: <FilesetNewRoute />,
                    },
                    {
                      path: ROUTES.workspace.filesetDetails,
                      element: <></>, // Just for URL matching - panel rendered in FilesetListRoute
                    },
                    {
                      path: ROUTES.workspace.filesetFile,
                      element: <></>, // Just for URL matching - panel rendered in FilesetListRoute
                    },
                  ],
                },
                ...gateFilesetDetailsRoutes([
                  {
                    path: ROUTES.workspace.datasetDetail,
                    element: (
                      <Suspense fallback={<Loading description="Loading Dataset..." />}>
                        <DatasetDetailRoute />
                      </Suspense>
                    ),
                    errorElement: <ErrorPanel title="Dataset" />,
                  },
                  {
                    path: ROUTES.workspace.modelDetail,
                    element: (
                      <Suspense fallback={<Loading description="Loading Model..." />}>
                        <ModelDetailRoute />
                      </Suspense>
                    ),
                    errorElement: <ErrorPanel title="Model" />,
                  },
                ]),
              ]),
              ...gateSecretsRoutes([
                {
                  path: ROUTES.workspace.secrets,
                  element: (
                    <Suspense fallback={<Loading />}>
                      <SecretsListRoute />
                    </Suspense>
                  ),
                  errorElement: <ErrorPanel title="Secrets" />,
                },
              ]),
              ...gateGuardrailsRoutes(
                GuardrailsRoute
                  ? {
                      path: ROUTES.workspace.guardrails,
                      element: (
                        <Suspense fallback={<Loading />}>
                          <GuardrailsRoute />
                        </Suspense>
                      ),
                      errorElement: <ErrorPanel title="Guardrails" />,
                    }
                  : []
              ),
              ...gateInferenceProviderRoutes([
                {
                  path: ROUTES.workspace.inferenceProviders,
                  element: (
                    <Suspense fallback={<Loading />}>
                      <InferenceProvidersListRoute />
                    </Suspense>
                  ),
                  errorElement: <ErrorPanel title="Inference Providers" />,
                },
              ]),
              ...gateDeploymentsRoutes([
                {
                  path: ROUTES.workspace.deployments,
                  element: DeploymentsListRoute ? (
                    <Suspense fallback={<Loading />}>
                      <DeploymentsListRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Deployments" />,
                },
                {
                  path: ROUTES.workspace.deploymentsDeployment,
                  element: DeploymentsListRoute ? (
                    <Suspense fallback={<Loading />}>
                      <DeploymentsListRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Deployments" />,
                },
              ]),
              ...gateEvaluationRoutes([
                {
                  path: ROUTES.workspace.evaluation,
                  element: <EvaluationLayout />,
                  errorElement: <ErrorPanel title="Evaluator" />,
                  children: [
                    {
                      index: true,
                      element: <Navigate to="metrics" replace />,
                    },
                    {
                      path: ROUTES.workspace.evaluationMetrics,
                      element: <EvaluationMetricsRoute />,
                    },
                    {
                      // Static "run" segment must appear before the dynamic :id route
                      path: ROUTES.workspace.evaluationMetricsRun,
                      element: <EvaluationMetricsRoute />,
                    },
                    {
                      path: ROUTES.workspace.evaluationMetricDetails,
                      element: <EvaluationMetricsRoute />,
                      children: [
                        {
                          // Nesting run under the details route keeps the same
                          // EvaluationMetricsRoute instance mounted when toggling
                          // between metrics/:id and metrics/:id/run, preventing
                          // the remount that caused panel transition errors.
                          path: 'run',
                          element: null,
                        },
                      ],
                    },
                    ...gateEvaluationBenchmarksRoutes([
                      {
                        path: ROUTES.workspace.evaluationBenchmarks,
                        element: <EvaluationBenchmarksRoute />,
                      },
                      {
                        path: ROUTES.workspace.evaluationBenchmarkDetails,
                        element: <EvaluationBenchmarksRoute />,
                        errorElement: <ErrorPanel title="Evaluator" />,
                      },
                    ]),
                  ],
                },
                {
                  path: ROUTES.workspace.evaluationMetricNew,
                  element: <NewEvaluationMetricRoute />,
                  errorElement: <ErrorPanel title="Evaluator" />,
                },
                {
                  path: ROUTES.workspace.evaluationResultDetails,
                  element: <EvaluationResultDetailsRoute />,
                  errorElement: <ErrorPanel title="Evaluator" />,
                },
                {
                  path: ROUTES.workspace.evaluationResults,
                  element: <EvaluationResultsLayout />,
                  errorElement: <ErrorPanel title="Evaluator" />,
                  children: [
                    {
                      index: true,
                      element: <EvaluationResultsRoute />,
                    },
                  ],
                },
              ]),
              ...gateCustomizationRoutes([
                {
                  path: ROUTES.workspace.promptTuningForm,
                  element: <PromptTuningFormRoute />,
                  errorElement: <ErrorPanel title="Customizer" />,
                },
                {
                  path: ROUTES.workspace.customizationJobList,
                  element: <CustomizationJobListRoute />,
                  errorElement: <ErrorPanel title="Customizer" />,
                },
                {
                  path: ROUTES.workspace.customizationJobDetails,
                  element: <CustomizationJobDetailsRoute />,
                  errorElement: <ErrorPanel title="Customizer" />,
                },
                {
                  path: ROUTES.workspace.newCustomizationJob,
                  element: (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <NewCustomizationRoute />
                    </Suspense>
                  ),
                  errorElement: <ErrorPanel title="Customizer" />,
                },
              ]),
              ...gateJobsRoutes([
                {
                  path: ROUTES.workspace.jobs,
                  element: <JobsRoute />,
                  errorElement: <ErrorPanel title="Jobs" />,
                },
                {
                  path: ROUTES.workspace.jobDetail,
                  element: <JobDetailRoute />,
                  errorElement: <ErrorPanel title="Job Details" />,
                },
              ]),
              ...gateIntakeRoutes([
                {
                  path: ROUTES.workspace.intake,
                  element: <IntakeLayout />,
                  errorElement: <ErrorPanel title="Intake" />,
                  children: [
                    {
                      index: true,
                      element: <Navigate to="traces" replace />,
                    },
                    {
                      path: ROUTES.workspace.intakeTraces,
                      element: <IntakeTracesTableRoute />,
                    },
                    {
                      path: ROUTES.workspace.intakeSpans,
                      element: <IntakeSpansTableRoute />,
                    },
                  ],
                },
                {
                  path: ROUTES.workspace.intakeTrace,
                  element: <IntakeTraceDetailRoute />,
                  errorElement: <ErrorPanel title="Intake" />,
                },
                {
                  path: ROUTES.workspace.intakeSpan,
                  element: <IntakeSpanDetailRoute />,
                  errorElement: <ErrorPanel title="Intake" />,
                },
              ]),
              ...gateSafeSynthesizerRoutes([
                {
                  path: ROUTES.workspace.safeSynthesizer,
                  element: SafeSynthesizerListRoute ? <SafeSynthesizerListRoute /> : null,
                  errorElement: <ErrorPanel title="Safe Synthesizer" />,
                },
                {
                  path: ROUTES.workspace.safeSynthesizerNew,
                  element: SafeSynthesizerNewRoute ? <SafeSynthesizerNewRoute /> : null,
                  errorElement: <ErrorPanel title="Safe Synthesizer" />,
                },
                {
                  path: ROUTES.workspace.safeSynthesizerJob,
                  element: SafeSynthesizerJobDetailsRoute ? (
                    <SafeSynthesizerJobDetailsRoute />
                  ) : null,
                  errorElement: <ErrorPanel title="Safe Synthesizer" />,
                },
                {
                  path: ROUTES.workspace.safeSynthesizerJobReport,
                  element: SafeSynthesizerJobReportRoute ? <SafeSynthesizerJobReportRoute /> : null,
                  errorElement: <ErrorPanel title="Safe Synthesizer" />,
                },
              ]),
              ...gateDataDesignerRoutes([
                {
                  path: ROUTES.workspace.dataDesignerJobList,
                  element: DataDesignerJobListRoute ? <DataDesignerJobListRoute /> : null,
                  errorElement: <ErrorPanel title="Data Designer" />,
                },
                {
                  path: ROUTES.workspace.dataDesignerJobDetails,
                  element: DataDesignerJobDetailsRoute ? <DataDesignerJobDetailsRoute /> : null,
                  errorElement: <ErrorPanel title="Data Designer" />,
                },
                {
                  path: ROUTES.workspace.dataDesignerJobNew,
                  element: NewDataDesignerJobRoute ? (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <NewDataDesignerJobRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Data Designer" />,
                },
              ]),
              ...agentsRoutes([
                {
                  path: ROUTES.workspace.agentsList,
                  element: AgentsListRoute ? <AgentsListRoute /> : null,
                  errorElement: <ErrorPanel title="Agents" />,
                },
                {
                  path: ROUTES.workspace.agentOptimizations,
                  element: AgentOptimizationsRoute ? (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <AgentOptimizationsRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Optimizations" />,
                },
                {
                  path: ROUTES.workspace.agentMonitor,
                  element: AgentMonitorRoute ? (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <AgentMonitorRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Monitor" />,
                },
                {
                  path: ROUTES.workspace.agentEvaluationsList,
                  element: AgentEvaluationsListRoute ? (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <AgentEvaluationsListRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Agent Evaluations" />,
                },
                {
                  path: ROUTES.workspace.agentEvaluationDetail,
                  element: AgentEvaluationDetailRoute ? (
                    <Suspense fallback={<Loading description="Loading..." />}>
                      <AgentEvaluationDetailRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Agent Evaluation" />,
                },
                {
                  path: ROUTES.workspace.agentDetail,
                  element: AgentsListRoute ? <AgentsListRoute /> : null,
                  errorElement: <ErrorPanel title="Agents" />,
                },
              ]),
              ...gateSettingsRoutes([
                {
                  path: ROUTES.workspace.settings,
                  element: (
                    <Suspense fallback={<Loading />}>
                      <WorkspaceSettingsRoute />
                    </Suspense>
                  ),
                  errorElement: <ErrorPanel title="Settings" />,
                },
              ]),
              ...gateModelCompareRoutes([
                {
                  path: ROUTES.workspace.modelCompare,
                  element: ModelCompareRoute ? (
                    <Suspense fallback={<Loading />}>
                      <ModelCompareRoute />
                    </Suspense>
                  ) : null,
                  errorElement: <ErrorPanel title="Model Compare" />,
                },
              ]),
              ...gateMembersRoutes([
                {
                  path: ROUTES.workspace.members,
                  element: (
                    <Suspense fallback={<Loading />}>
                      <WorkspaceMembersRoute />
                    </Suspense>
                  ),
                  errorElement: <ErrorPanel title="Members" />,
                },
              ]),
            ],
          },
        ],
      },
      {
        path: '*',
        element: <NoMatchRoute />,
      },
    ],
  },
];
