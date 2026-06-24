// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Root as DataView } from '@nemo/common/src/components/DataView/internal';
import { useStudioDataViewState } from '@nemo/common/src/hooks/useStudioDataViewState';
import { useAgentsListAgents } from '@nemo/sdk/generated/agents/api';
import { useWorkspaceFromPath } from '@studio/hooks/useWorkspaceFromPath';
import { useBreadcrumbs } from '@studio/providers/breadcrumbs/useBreadcrumbs';
import { loadSnapshot } from '@studio/routes/agents/AgentSuggestionsRoute/api';
import {
  SCOPE_AGENT,
  SCOPE_OPTIONS,
  SCOPE_WORKSPACE,
  SEVERITY_ORDER,
  STALE_SUGGESTION_MS,
  TYPE_OPTIONS,
} from '@studio/routes/agents/AgentSuggestionsRoute/constants';
import type {
  EvalConfigChoice,
  OptimizationSuggestion,
} from '@studio/routes/agents/AgentSuggestionsRoute/types';
import { useOptimizerSuggestions } from '@studio/routes/agents/AgentSuggestionsRoute/useOptimizerSuggestions';
import {
  capitalize,
  countSeverities,
  snapshotAgentNames,
  snapshotModelNames,
} from '@studio/routes/agents/AgentSuggestionsRoute/utils';
import { getAgentsListRoute } from '@studio/routes/utils';
import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from 'react';
import { useLocation } from 'react-router-dom';

type MultiState = Record<string, true>;
interface SuggestionFilter {
  agent?: MultiState;
  severity?: MultiState;
  type?: MultiState;
  scope?: MultiState;
}

export const useAgentOptimizations = () => {
  const workspace = useWorkspaceFromPath();
  const location = useLocation();
  const {
    suggestions,
    previousSuggestions,
    isSuggestionsLoading,
    suggestionsLoadError,
    refetchSuggestions,
    phase,
    step,
    error,
    run,
    apply,
    getApplyState,
    getEvalState,
  } = useOptimizerSuggestions(workspace);

  const snapshotQuery = useQuery({
    queryKey: ['agent-optimizer', 'snapshot', workspace] as const,
    queryFn: ({ signal }) => loadSnapshot(workspace, signal),
    enabled: !!workspace,
    retry: false,
  });
  const snapshot = snapshotQuery.data ?? null;

  // Workspace agent count drives whether auto-run fires and which empty
  // state we show — running the optimizer against zero agents is pointless.
  const agentsListQuery = useAgentsListAgents(
    workspace,
    { page: 1, page_size: 1 },
    { query: { enabled: !!workspace } }
  );
  const totalAgentsInWorkspace =
    agentsListQuery.data?.pagination?.total_results ?? agentsListQuery.data?.data?.length ?? 0;
  const hasAgentsInWorkspace = totalAgentsInWorkspace > 0;

  const breadcrumbItems = useMemo(
    () => [
      { slotLabel: 'Agents', href: getAgentsListRoute(workspace) },
      { slotLabel: 'Optimizations' },
    ],
    [workspace]
  );
  useBreadcrumbs({ items: breadcrumbItems });

  const isSnapshotStale = useMemo(() => {
    if (!snapshot?.agents) return false;
    const timestamps = Object.values(snapshot.agents)
      .map((a) => Date.parse(a.updatedAt))
      .filter((t) => !Number.isNaN(t));
    if (timestamps.length === 0) return false;
    return Date.now() - Math.max(...timestamps) > STALE_SUGGESTION_MS;
  }, [snapshot]);

  const didAutoRun = useRef(false);
  // Reset the auto-run guard when the workspace changes so the next workspace
  // visited gets its own initial run.
  useEffect(() => {
    didAutoRun.current = false;
  }, [workspace]);
  useEffect(() => {
    if (didAutoRun.current) return;
    if (isSuggestionsLoading || snapshotQuery.isLoading || agentsListQuery.isLoading) return;
    if (!hasAgentsInWorkspace) return;
    const fromNav = (location.state as { autoRun?: boolean } | null)?.autoRun;
    const isEmptyFirstLoad = !suggestionsLoadError && suggestions.length === 0;
    if (fromNav || isEmptyFirstLoad || isSnapshotStale) {
      didAutoRun.current = true;
      void run();
    }
  }, [
    isSuggestionsLoading,
    snapshotQuery.isLoading,
    agentsListQuery.isLoading,
    hasAgentsInWorkspace,
    suggestionsLoadError,
    suggestions.length,
    isSnapshotStale,
    location.state,
    run,
  ]);

  const isRunning = phase === 'running';

  const [showFilters, setShowFilters] = useState(false);
  const [agentSearch, setAgentSearch] = useState('');
  // Suggestion the user just clicked Apply on — drives the eval-config
  // chooser modal. ``null`` keeps the modal closed.
  const [pendingApply, setPendingApply] = useState<OptimizationSuggestion | null>(null);
  const dataViewState = useStudioDataViewState<SuggestionFilter>({});

  const handleApplyClicked = useCallback(
    (suggestion: OptimizationSuggestion) => {
      // Only ``model_optimization`` suggestions actually run an eval — for
      // everything else (guardrails, data_safety, new_model_scan) there's
      // nothing for the user to choose, so apply immediately.
      if (suggestion.type === 'model_optimization' && suggestion.agent) {
        setPendingApply(suggestion);
        return;
      }
      void apply(suggestion);
    },
    [apply]
  );

  const handleEvalConfigChosen = useCallback(
    (choice: EvalConfigChoice) => {
      const target = pendingApply;
      setPendingApply(null);
      if (!target) return;
      void apply(
        target,
        choice.filesetOverride ? { evalConfigOverride: choice.filesetOverride } : undefined
      );
    },
    [apply, pendingApply]
  );

  // Single pass over ``suggestions`` builds the four filter dropdown
  // option sets — replaces four independent ``useMemo``s that each iterated
  // the array.
  const { agentOptions, scopeOptions, severityOptions, typeOptions } = useMemo(() => {
    const agents = new Set<string>();
    const scopes = new Set<string>();
    const severities = new Set<string>();
    const types = new Set<string>();
    for (const s of suggestions) {
      if (s.agent) agents.add(s.agent);
      scopes.add(s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE);
      severities.add(s.severity ?? 'low');
      types.add(s.type);
    }
    return {
      agentOptions: Array.from(agents)
        .sort()
        .map((value) => ({ value, label: value })),
      scopeOptions: SCOPE_OPTIONS.filter((opt) => scopes.has(opt.value)),
      severityOptions: Array.from(severities)
        .sort((a, b) => (SEVERITY_ORDER[a] ?? 99) - (SEVERITY_ORDER[b] ?? 99))
        .map((value) => ({ value, label: capitalize(value) })),
      typeOptions: TYPE_OPTIONS.filter((opt) => types.has(opt.value)),
    };
  }, [suggestions]);

  const makeColumns = useCallback<
    NonNullable<ComponentProps<typeof DataView<OptimizationSuggestion>>['makeColumns']>
  >(
    ({ accessor }) => [
      accessor((s: OptimizationSuggestion) => s.type, {
        id: 'type',
        header: 'Type',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Type',
            options: typeOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => s.severity ?? 'low', {
        id: 'severity',
        header: 'Priority',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Priority',
            options: severityOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => (s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE), {
        id: 'scope',
        header: 'Scope',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Scope',
            options: scopeOptions,
          },
        },
      }),
      accessor((s: OptimizationSuggestion) => s.agent ?? '', {
        id: 'agent',
        header: 'Agent',
        enableSorting: false,
        meta: {
          filter: {
            type: 'multi-select',
            label: 'Agent',
            options: agentOptions,
          },
        },
      }),
    ],
    [typeOptions, severityOptions, scopeOptions, agentOptions]
  );

  const filterState = dataViewState.apiFilter.filter;
  const agentFilter = filterState?.agent;
  const severityFilter = filterState?.severity;
  const typeFilter = filterState?.type;
  const scopeFilter = filterState?.scope;

  const filteredSuggestions = useMemo(() => {
    const agentKeys = agentFilter ? Object.keys(agentFilter) : [];
    const severityKeys = severityFilter ? Object.keys(severityFilter) : [];
    const typeKeys = typeFilter ? Object.keys(typeFilter) : [];
    const scopeKeys = scopeFilter ? Object.keys(scopeFilter) : [];
    return suggestions.filter((s) => {
      if (agentKeys.length > 0) {
        if (!s.agent || !agentFilter?.[s.agent]) return false;
      }
      if (scopeKeys.length > 0) {
        const scope = s.agent ? SCOPE_AGENT : SCOPE_WORKSPACE;
        if (!scopeFilter?.[scope]) return false;
      }
      if (severityKeys.length > 0 && !severityFilter?.[s.severity ?? 'low']) return false;
      if (typeKeys.length > 0 && !typeFilter?.[s.type]) return false;
      return true;
    });
  }, [suggestions, agentFilter, severityFilter, typeFilter, scopeFilter]);

  // Workspace-wide suggestions sit above per-agent groups in the layout.
  const workspaceSuggestions = useMemo(
    () => filteredSuggestions.filter((s) => !s.agent),
    [filteredSuggestions]
  );

  // Group agent-scoped suggestions by agent name. Track all referenced models
  // per agent so multi-model agents match search against any of their models;
  // also expose the first model as a primary label for the accordion trigger.
  const agentGroups = useMemo(() => {
    const groups = new Map<string, { items: OptimizationSuggestion[]; models: Set<string> }>();
    for (const s of filteredSuggestions) {
      if (!s.agent) continue;
      let group = groups.get(s.agent);
      if (!group) {
        group = { items: [], models: new Set() };
        groups.set(s.agent, group);
      }
      group.items.push(s);
      if (s.model) group.models.add(s.model);
    }
    return Array.from(groups.entries())
      .map(([name, value]) => ({
        name,
        items: value.items,
        models: Array.from(value.models),
      }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [filteredSuggestions]);

  const visibleAgentGroups = useMemo(() => {
    const q = agentSearch.trim().toLowerCase();
    if (!q) return agentGroups;
    return agentGroups.filter(
      (g) => g.name.toLowerCase().includes(q) || g.models.some((m) => m.toLowerCase().includes(q))
    );
  }, [agentGroups, agentSearch]);

  const stats = useMemo(() => {
    const snapshotAgents = snapshotAgentNames(snapshot);
    const snapshotModels = snapshotModelNames(snapshot);
    const agentCount = snapshotAgents.length || agentGroups.length;
    const modelCount =
      snapshotModels.length ||
      new Set(suggestions.map((s) => s.model).filter((m): m is string => !!m)).size;
    return { agentCount, modelCount, ...countSeverities(suggestions) };
  }, [snapshot, agentGroups.length, suggestions]);

  const previousStats = useMemo(() => countSeverities(previousSuggestions), [previousSuggestions]);
  const hasPreviousRun = previousSuggestions.length > 0;

  const hasSuggestions = suggestions.length > 0;
  const showStats = stats.agentCount > 0 && (hasSuggestions || snapshot !== null);

  return {
    workspace,
    isSuggestionsLoading,
    suggestionsLoadError,
    refetchSuggestions,
    phase,
    step,
    error,
    run,
    apply,
    getApplyState,
    getEvalState,
    agentsListQuery,
    hasAgentsInWorkspace,
    isRunning,
    showFilters,
    setShowFilters,
    agentSearch,
    setAgentSearch,
    pendingApply,
    setPendingApply,
    dataViewState,
    handleApplyClicked,
    handleEvalConfigChosen,
    makeColumns,
    filteredSuggestions,
    workspaceSuggestions,
    agentGroups,
    visibleAgentGroups,
    stats,
    previousStats,
    hasPreviousRun,
    hasSuggestions,
    showStats,
    suggestions,
  };
};
