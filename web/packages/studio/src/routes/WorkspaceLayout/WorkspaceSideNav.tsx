// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { logger } from '@nemo/common/src/utils/logger';
import { NavigationDrawer } from '@studio/components/Layouts/NavigationDrawer';
import type {
  NavInputItem,
  NavItem as NavItemData,
} from '@studio/components/Layouts/NavigationDrawer/types';
import { isGroup } from '@studio/components/Layouts/NavigationDrawer/utils';
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

/** Whether the path is on, or nested under, one of these items. */
const isUnder = (pathname: string, items: { href?: string }[]) =>
  items.some(
    (item) =>
      item.href !== undefined && (pathname === item.href || pathname.startsWith(`${item.href}/`))
  );

const eachItem = (entries: NavInputItem[]): NavItemData[] =>
  entries.flatMap((entry) => (isGroup(entry) ? entry.items : [entry]));

/** A parent starts expanded when the current page is its own landing page or one of its children. */
const ownsCurrentPage = (item: NavItemData, pathname: string) =>
  isUnder(pathname, [{ href: item.href }, ...(item.subItems ?? [])]);

/**
 * The ids of every expanded parent, joined into one string. Navigating deeper inside a section
 * leaves this untouched, which is what lets `withDefaultOpen` hand back the identical tree.
 */
const openParentKey = (entries: NavInputItem[], pathname: string): string =>
  eachItem(entries)
    .filter((item) => item.subItems !== undefined && ownsCurrentPage(item, pathname))
    .map((item) => item.id)
    .join('|');

/**
 * Stamp `defaultOpen` onto the parents named by `openIds`. Kept apart from building the tree so a
 * navigation rewrites a few parent objects instead of rebuilding every leaf and icon.
 */
const withDefaultOpen = (entries: NavInputItem[], openIds: string): NavInputItem[] => {
  const open = new Set(openIds.split('|'));
  const stamp = (item: NavItemData): NavItemData =>
    item.subItems === undefined ? item : { ...item, defaultOpen: open.has(item.id) };
  return entries.map((entry) =>
    isGroup(entry) ? { ...entry, items: entry.items.map(stamp) } : stamp(entry)
  );
};

export const WorkspaceSideNav = ({ collapsed }: { collapsed?: boolean }) => {
  const workspace = useWorkspaceFromPath();
  const { pathname } = useLocation();
  const plugins = usePlugins();
  const agentsInstalled = usePluginInstalled('agents');
  const pluginsLoaded = usePluginsLoaded();
  const pluginsError = usePluginsError();
  const manifestResolved = pluginsLoaded && !pluginsError;
  const showAgents = agentsInstalled || !manifestResolved;

  const baseItems = useMemo<NavInputItem[]>(() => {
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
            // Qualified: the rail hoists this out of Models, next to the agent evaluations link.
            slotLabel: 'Model Evaluations',
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
  }, [workspace, showAgents]);

  const openIds = useMemo(() => openParentKey(baseItems, pathname), [baseItems, pathname]);
  const items = useMemo(() => withDefaultOpen(baseItems, openIds), [baseItems, openIds]);

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

  // A fresh array literal here would re-run NavigationDrawer's own memos on every render.
  const allItems = useMemo(
    () => [...items, ...pluginNavGroups, ...systemNavGroup],
    [items, pluginNavGroups, systemNavGroup]
  );

  return <NavigationDrawer items={allItems} collapsed={collapsed} />;
};
