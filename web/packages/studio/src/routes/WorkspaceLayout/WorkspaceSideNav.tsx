// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { NavigationDrawer } from '@studio/components/Layouts/NavigationDrawer';
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
  getAgentsListRoute,
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
  Bot,
  Boxes,
  ChartBar,
  Database,
  ListChecks,
  Rocket,
  Waypoints,
  LayoutDashboard,
  Lightbulb,
  ListTree,
  CirclePlay,
  Metronome,
  FlaskConical,
  Form,
  DatabaseCheck,
  UserPen,
  ShieldKeyhole,
  FileStack,
  Settings,
} from 'lucide-react';
import { useMemo } from 'react';
import { useLocation } from 'react-router';

/** Whether the current path sits on or under any of these items, so its parent starts expanded. */
const isUnder = (pathname: string, items: { href?: string }[]) =>
  items.some(
    (item) =>
      item.href !== undefined && (pathname === item.href || pathname.startsWith(`${item.href}/`))
  );

export const WorkspaceSideNav = ({ collapsed }: { collapsed?: boolean }) => {
  const workspace = useWorkspaceFromPath();
  const { pathname } = useLocation();
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
              slotIcon: <LayoutDashboard className={iconColorClass} />,
              slotLabel: 'Dashboard',
              href: getWorkspaceDashboardRoute(workspace),
            },
          ]
        : [];
    const customizerNav = CUSTOMIZER_ENABLED
      ? [
          {
            id: 'custom-models',
            slotIcon: <Metronome className={iconColorClass} />,
            slotLabel: 'Fine-tune',
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
            slotIcon: <ListTree className={iconColorClass} />,
            slotLabel: 'Traces',
            href: getIntakeTracesRoute(workspace),
          },
        ]
      : [];

    const experimentNav = EXPERIMENT_ENABLED
      ? [
          {
            id: 'experiment',
            slotIcon: <FlaskConical className={iconColorClass} />,
            slotLabel: 'Experiments',
            href: getExperimentRoute(workspace),
          },
        ]
      : [];

    const safeSynthesizerNav = SAFE_SYNTHESIZER_ENABLED
      ? [
          {
            id: 'safeSynthesizer',
            slotIcon: <DatabaseCheck className={iconColorClass} />,
            slotLabel: 'Safe Synthesizer',
            href: getWorkspaceSafeSynthesizerRoute(workspace),
          },
        ]
      : [];

    const dataDesignerNav = DATA_DESIGNER_ENABLED
      ? [
          {
            id: 'data-designer',
            slotIcon: <Form className={iconColorClass} />,
            slotLabel: 'Data Designer',
            href: getDataDesignerJobListRoute(workspace),
          },
        ]
      : [];

    const anonymizerNav = ANONYMIZER_ENABLED
      ? [
          {
            id: 'anonymizer',
            slotIcon: <UserPen className={iconColorClass} />,
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
            slotIcon: <Lightbulb className={iconColorClass} />,
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
            slotIcon: <CirclePlay className={iconColorClass} />,
            slotLabel: 'Playground',
            href: getModelCompareRoute(workspace),
          },
        ]
      : [];

    const deploymentsNav = DEPLOYMENTS_ENABLED
      ? [
          {
            id: 'deployments',
            slotIcon: <Rocket className={iconColorClass} />,
            slotLabel: 'Deployments',
            href: getWorkspaceDeploymentsRoute(workspace),
          },
        ]
      : [];

    const observabilityItems = [...optimizerNav, ...tracesNav];

    const modelSubItems = [
      ...modelCompareNav,
      ...evalNav,
      ...customizerNav,
      ...virtualModelsNav,
      ...deploymentsNav,
    ];
    const datasetSubItems = [...dataDesignerNav, ...safeSynthesizerNav, ...anonymizerNav];

    // Agents and Models link to their own entity list page; the chevron expands the rest.
    const agentsHref = agentItems.length > 0 ? getAgentsListRoute(workspace) : undefined;
    const modelsHref = BASE_MODELS_ENABLED ? getWorkspaceBaseModelsRoute(workspace) : undefined;

    const componentItems = [
      ...(agentsHref !== undefined
        ? [
            {
              id: 'agents-group',
              slotIcon: <Bot className={iconColorClass} />,
              slotLabel: 'Agents',
              href: agentsHref,
              defaultOpen: isUnder(pathname, [{ href: agentsHref }, ...agentItems]),
              subItems: agentItems,
            },
          ]
        : []),
      ...(modelsHref !== undefined || modelSubItems.length > 0
        ? [
            {
              id: 'models-group',
              slotIcon: <Boxes className={iconColorClass} />,
              slotLabel: 'Models',
              href: modelsHref,
              defaultOpen: isUnder(pathname, [{ href: modelsHref }, ...modelSubItems]),
              subItems: modelSubItems,
            },
          ]
        : []),
    ];

    const dataItems =
      datasetSubItems.length > 0
        ? [
            {
              id: 'datasets-group',
              slotIcon: <Database className={iconColorClass} />,
              slotLabel: 'Datasets',
              defaultOpen: isUnder(pathname, datasetSubItems),
              subItems: datasetSubItems,
            },
          ]
        : [];

    const governanceItems = GUARDRAILS_ENABLED
      ? [
          {
            id: 'guardrails',
            slotIcon: <ShieldKeyhole className={iconColorClass} />,
            slotLabel: 'Guardrails',
            href: getGuardrailsRoute(workspace),
          },
        ]
      : [];

    return [
      ...dashboardNav,
      ...(observabilityItems.length > 0
        ? [{ group: 'Observability', items: observabilityItems }]
        : []),
      ...(componentItems.length > 0 ? [{ group: 'Components', items: componentItems }] : []),
      ...(experimentNav.length > 0 ? [{ group: 'Evaluations', items: experimentNav }] : []),
      ...(dataItems.length > 0 ? [{ group: 'Data', items: dataItems }] : []),
      ...(governanceItems.length > 0 ? [{ group: 'Governance', items: governanceItems }] : []),
    ];
  }, [workspace, showAgents, pathname]);

  const systemNavGroup = useMemo(() => {
    const systemItems = [
      ...(JOBS_ENABLED
        ? [
            {
              id: 'jobs',
              slotIcon: <ListChecks className={iconColorClass} />,
              slotLabel: 'Jobs',
              href: getWorkspaceJobsRoute(workspace),
            },
          ]
        : []),
      ...(DATASETS_ENABLED
        ? [
            {
              id: 'datasets',
              slotIcon: <FileStack className={iconColorClass} />,
              slotLabel: 'Filesets',
              href: getWorkspaceFilesetsRoute(workspace),
            },
          ]
        : []),
      ...(SETTINGS_ENABLED
        ? [
            {
              id: 'settings',
              slotIcon: <Settings className={iconColorClass} />,
              slotLabel: 'Settings',
              href: getWorkspaceSettingsRoute(workspace),
            },
          ]
        : []),
    ];
    return systemItems.length > 0 ? [{ group: 'System', items: systemItems }] : [];
  }, [workspace]);

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
      items={[...items, ...pluginNavGroups, ...systemNavGroup]}
      collapsed={collapsed}
    />
  );
};
