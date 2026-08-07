// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import SafeSynthesizerLogo from '@nemo/common/src/svgs/safe_synthesizer_logo.svg?react';
import { NavigationDrawer } from '@studio/components/Layouts/NavigationDrawer';
import { DataDesignerIconFc } from '@studio/constants/constants';
import {
  ANONYMIZER_ENABLED,
  BASE_MODELS_ENABLED,
  COPILOT_STUDIO_ENABLED,
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
  OPTIMIZER_ENABLED,
  SAFE_SYNTHESIZER_ENABLED,
  SETTINGS_ENABLED,
} from '@studio/constants/environment';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { getPluginIcon } from '@studio/plugins/iconMap';
import {
  usePluginInstalled,
  usePlugins,
  usePluginsError,
  usePluginsLoaded,
} from '@studio/plugins/PluginContext';
import { iconColorClass } from '@studio/routes/constants';
import { getAgentSideNavItems } from '@studio/routes/groups/agentRoutes';
import {
  getWorkspaceAnonymizerRoute,
  getDataDesignerJobListRoute,
  getEvaluationResultsRoute,
  getExperimentRoute,
  getGuardrailsRoute,
  getIntakeTracesRoute,
  getModelCompareRoute,
  getOptimizerRoute,
  getWorkspaceBaseModelsRoute,
  getWorkspaceCustomizationJobListRoute,
  getWorkspaceDashboardRoute,
  getWorkspaceFilesetsRoute,
  getWorkspaceDeploymentsRoute,
  getWorkspaceJobsRoute,
  getWorkspaceSafeSynthesizerRoute,
  getWorkspaceSettingsRoute,
  getWorkspaceVirtualModelsRoute,
} from '@studio/routes/utils';
import { logger } from '@studio/util/logger';
import {
  Beaker,
  Boxes,
  ChartBar,
  Database,
  ListChecks,
  Home,
  ShieldCheck,
  Sliders,
  Activity,
  Cog,
  Columns3,
  Rocket,
  VenetianMask,
  Gauge,
  Waypoints,
} from 'lucide-react';
import { useMemo } from 'react';

export const WorkspaceSideNav = ({ collapsed }: { collapsed?: boolean }) => {
  const workspace = useWorkspaceFromPath();
  const plugins = usePlugins();
  const agentsInstalled = usePluginInstalled('agents');
  const pluginsLoaded = usePluginsLoaded();
  const pluginsError = usePluginsError();
  const manifestResolved = pluginsLoaded && !pluginsError;
  const showAgents = agentsInstalled || !manifestResolved;

  const items = useMemo(() => {
    const dashboardNav =
      DASHBOARD_ENABLED || COPILOT_STUDIO_ENABLED
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

    const tracesNav = INTAKE_ENABLED
      ? [
          {
            id: 'traces',
            slotIcon: <Activity className={iconColorClass} />,
            slotLabel: 'Traces',
            href: getIntakeTracesRoute(workspace),
          },
        ]
      : [];

    const experimentNav = EXPERIMENT_ENABLED
      ? [
          {
            id: 'experiment',
            slotIcon: <Beaker className={iconColorClass} />,
            slotLabel: 'Experiments',
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
            slotIcon: <DataDesignerIconFc className={iconColorClass} />,
            slotLabel: 'Data Designer',
            href: getDataDesignerJobListRoute(workspace),
          },
        ]
      : [];

    const anonymizerNav = ANONYMIZER_ENABLED
      ? [
          {
            id: 'anonymizer',
            slotIcon: <VenetianMask className={iconColorClass} />,
            slotLabel: 'Anonymizer',
            href: getWorkspaceAnonymizerRoute(workspace),
          },
        ]
      : [];

    const agentItems = showAgents ? getAgentSideNavItems(workspace) : [];

    const optimizerNav = OPTIMIZER_ENABLED
      ? [
          {
            id: 'optimizer',
            slotIcon: <Gauge className={iconColorClass} />,
            slotLabel: 'Insights',
            href: getOptimizerRoute(workspace),
          },
        ]
      : [];
    const virtualModelsNav = [
      {
        id: 'virtual-models',
        slotIcon: <Waypoints className={iconColorClass} />,
        slotLabel: 'Virtual Models',
        href: getWorkspaceVirtualModelsRoute(workspace),
      },
    ];

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
      ...anonymizerNav,
    ];
    const evaluateItems = [...evalNav, ...tracesNav, ...experimentNav];

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
      ...(agentItems.length > 0 || optimizerNav.length > 0
        ? [
            {
              group: 'Agents',
              items: [...agentItems, ...optimizerNav],
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
          ...virtualModelsNav,
        ],
      },
      ...(dataItems.length > 0 ? [{ group: 'Data', items: dataItems }] : []),
      ...(evaluateItems.length > 0 ? [{ group: 'Evaluate', items: evaluateItems }] : []),
      ...(safetyItems.length > 0 ? [{ group: 'Safety', items: safetyItems }] : []),
    ];
  }, [workspace, showAgents]);

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

  const pluginNavGroups = useMemo(
    () =>
      plugins.flatMap((plugin) => {
        try {
          return plugin.navItems(workspace).map((group) => ({
            group: group.group,
            items: group.items.map((item) => {
              const Icon = getPluginIcon(item.iconName);
              return {
                id: item.id,
                slotIcon: Icon ? <Icon className={iconColorClass} /> : undefined,
                slotLabel: item.label,
                href: item.href,
              };
            }),
          }));
        } catch (err) {
          logger.warn(`[plugins] navItems() threw for plugin "${plugin.name}":`, err);
          return [];
        }
      }),
    [plugins, workspace]
  );

  return (
    <NavigationDrawer
      items={[...items, ...pluginNavGroups]}
      bottomItems={bottomItems}
      collapsed={collapsed}
    />
  );
};
