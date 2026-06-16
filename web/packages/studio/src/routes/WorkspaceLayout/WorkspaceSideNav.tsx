// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import SafeSynthesizerLogo from '@nemo/common/src/svgs/safe_synthesizer_logo.svg?react';
import { NavigationDrawer } from '@studio/components/Layouts/NavigationDrawer';
import {
  AGENTS_ENABLED,
  BASE_MODELS_ENABLED,
  CODING_AGENT_STUDIO_ENABLED,
  CUSTOMIZER_ENABLED,
  DASHBOARD_ENABLED,
  DATA_DESIGNER_ENABLED,
  DATASETS_ENABLED,
  DEPLOYMENTS_ENABLED,
  EVALUATOR_ENABLED,
  EXPERIMENT_ENABLED,
  GUARDRAILS_ENABLED,
  INTAKE_ENABLED,
  JOBS_ENABLED,
  MODEL_COMPARE_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
  SETTINGS_ENABLED,
} from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { iconColorClass } from '@studio/routes/constants';
import {
  getAgentEvaluationsListRoute,
  getAgentsListRoute,
  getAgentMonitorRoute,
  getAgentOptimizationsRoute,
  getDataDesignerJobListRoute,
  getModelCompareRoute,
  getEvaluationResultsRoute,
  getExperimentRoute,
  getGuardrailsRoute,
  getIntakeRoute,
  getWorkspaceBaseModelsRoute,
  getWorkspaceCustomizationJobListRoute,
  getWorkspaceDashboardRoute,
  getWorkspaceFilesetsRoute,
  getWorkspaceDeploymentsRoute,
  getWorkspaceJobsRoute,
  getWorkspaceSafeSynthesizerRoute,
  getWorkspaceSettingsRoute,
} from '@studio/routes/utils';
import {
  Beaker,
  Boxes,
  ChartBar,
  Database,
  HatGlasses,
  LayoutList,
  ListChecks,
  Home,
  ShieldCheck,
  Sliders,
  UserPen,
  Cog,
  Columns3,
  Rocket,
  Lightbulb,
  Activity,
  FlaskConical,
} from 'lucide-react';
import { useMemo } from 'react';

export const WorkspaceSideNav = ({ collapsed }: { collapsed?: boolean }) => {
  const workspace = useWorkspaceFromPath();

  const items = useMemo(() => {
    const dashboardNav =
      DASHBOARD_ENABLED || CODING_AGENT_STUDIO_ENABLED
        ? [
            {
              id: 'dashboard',
              slotIcon: <Home className={iconColorClass} />,
              slotLabel: 'Dashboard',
              href: getWorkspaceDashboardRoute(workspace),
            },
          ]
        : [];
    const jobsNav = JOBS_ENABLED
      ? [
          {
            id: 'jobs',
            slotIcon: <ListChecks className={iconColorClass} />,
            slotLabel: 'Jobs',
            href: getWorkspaceJobsRoute(workspace),
          },
        ]
      : [];
    const customizerNav = CUSTOMIZER_ENABLED
      ? [
          {
            id: 'custom-models',
            slotIcon: <Sliders className={iconColorClass} />,
            slotLabel: 'Custom Models',
            href: getWorkspaceCustomizationJobListRoute(workspace),
          },
        ]
      : [];

    const evalNav = EVALUATOR_ENABLED
      ? [
          {
            id: 'evaluation-results',
            slotIcon: <ChartBar className={iconColorClass} />,
            slotLabel: 'Evaluations',
            href: getEvaluationResultsRoute(workspace),
          },
        ]
      : [];

    const intakeNav = INTAKE_ENABLED
      ? [
          {
            id: 'annotation',
            slotIcon: <UserPen className={iconColorClass} />,
            slotLabel: 'Annotation',
            href: getIntakeRoute(workspace),
          },
        ]
      : [];

    const experimentNav = EXPERIMENT_ENABLED
      ? [
          {
            id: 'experiment',
            slotIcon: <Beaker className={iconColorClass} />,
            slotLabel: 'Experiment',
            href: getExperimentRoute(workspace),
          },
        ]
      : [];

    const safeSynthesizerNav = SAFE_SYNTHESIZER_ENABLED
      ? [
          {
            id: 'safeSynthesizer',
            slotIcon: <SafeSynthesizerLogo className={iconColorClass} />,
            slotLabel: 'Safe Synthesizer',
            href: getWorkspaceSafeSynthesizerRoute(workspace),
          },
        ]
      : [];

    const dataDesignerNav = DATA_DESIGNER_ENABLED
      ? [
          {
            id: 'data-designer',
            slotIcon: <LayoutList className={iconColorClass} />,
            slotLabel: 'Data Designer',
            href: getDataDesignerJobListRoute(workspace),
          },
        ]
      : [];

    const agentsNav = AGENTS_ENABLED
      ? [
          {
            id: 'agents',
            slotIcon: <HatGlasses className={iconColorClass} />,
            slotLabel: 'Agents',
            href: getAgentsListRoute(workspace),
          },
          {
            id: 'agent-evaluations',
            slotIcon: <FlaskConical className={iconColorClass} />,
            slotLabel: 'Evaluations',
            href: getAgentEvaluationsListRoute(workspace),
          },
          {
            id: 'agent-monitor',
            slotIcon: <Activity className={iconColorClass} />,
            slotLabel: 'Monitor',
            href: getAgentMonitorRoute(workspace),
          },

          {
            id: 'agent-optimizations',
            slotIcon: <Lightbulb className={iconColorClass} />,
            slotLabel: 'Suggestions',
            href: getAgentOptimizationsRoute(workspace),
          },
        ]
      : [];

    const modelCompareNav = MODEL_COMPARE_ENABLED
      ? [
          {
            id: 'playground',
            slotIcon: <Columns3 className={iconColorClass} />,
            slotLabel: 'Playground',
            href: getModelCompareRoute(workspace),
          },
        ]
      : [];

    const dataItems = [
      ...(DATASETS_ENABLED
        ? [
            {
              id: 'datasets',
              slotIcon: <Database className={iconColorClass} />,
              slotLabel: 'Filesets',
              href: getWorkspaceFilesetsRoute(workspace),
            },
          ]
        : []),
      ...safeSynthesizerNav,
      ...dataDesignerNav,
    ];
    const evaluateItems = [...evalNav, ...intakeNav, ...experimentNav];

    const safetyItems = GUARDRAILS_ENABLED
      ? [
          {
            id: 'guardrails',
            slotIcon: <ShieldCheck className={iconColorClass} />,
            slotLabel: 'Guardrails',
            href: getGuardrailsRoute(workspace),
          },
        ]
      : [];

    return [
      ...dashboardNav,
      ...modelCompareNav,
      ...(agentsNav.length > 0
        ? [
            {
              group: 'Agents',
              items: agentsNav,
            },
          ]
        : []),
      ...(jobsNav.length > 0
        ? [
            {
              group: 'Jobs',
              items: jobsNav,
            },
          ]
        : []),
      ...(BASE_MODELS_ENABLED || customizerNav.length > 0 || DEPLOYMENTS_ENABLED
        ? [
            {
              group: 'Models',
              items: [
                ...(BASE_MODELS_ENABLED
                  ? [
                      {
                        id: 'models',
                        slotIcon: <Boxes className={iconColorClass} />,
                        slotLabel: 'Base Models',
                        href: getWorkspaceBaseModelsRoute(workspace),
                      },
                    ]
                  : []),
                ...customizerNav,
                ...(DEPLOYMENTS_ENABLED
                  ? [
                      {
                        id: 'deployments',
                        slotIcon: <Rocket className={iconColorClass} />,
                        slotLabel: 'Deployments',
                        href: getWorkspaceDeploymentsRoute(workspace),
                      },
                    ]
                  : []),
              ],
            },
          ]
        : []),
      ...(dataItems.length > 0 ? [{ group: 'Data', items: dataItems }] : []),
      ...(evaluateItems.length > 0 ? [{ group: 'Evaluate', items: evaluateItems }] : []),
      ...(safetyItems.length > 0 ? [{ group: 'Safety', items: safetyItems }] : []),
    ];
  }, [workspace]);

  const bottomItems = useMemo(
    () => [
      ...(SETTINGS_ENABLED
        ? [
            {
              id: 'settings',
              slotIcon: <Cog className={iconColorClass} />,
              slotLabel: 'Settings',
              href: getWorkspaceSettingsRoute(workspace),
            },
          ]
        : []),
    ],
    [workspace]
  );

  return <NavigationDrawer items={items} bottomItems={bottomItems} collapsed={collapsed} />;
};
