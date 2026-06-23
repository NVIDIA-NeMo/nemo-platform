// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import type {
  ExperimentResponse,
  ExperimentSessionResponse,
} from '@nemo/sdk/generated/platform/schema';
import type { ComponentType } from 'react';

/**
 * The source of truth for the plugin slot system. Every named slot maps to the typed
 * context object its contributed components receive as props.
 *
 * To define a new slot: add an entry here, drop a `<PluginSlot slot="..." context={...} />`
 * at the host site, and TypeScript keeps the host and every contributor in agreement.
 */
export interface SlotContextMap {
  /** Above the search bar and filters on the experiment group page. */
  'experiments.group.beforeSearch': {
    workspace: string;
    experimentGroupName: string;
    experimentGroupId: string;
    totalCount: number;
    /** The experiment rows currently in the table view (the loaded page, post-search/filter). */
    experiments: readonly ExperimentResponse[];
  };
  /** Between the search bar and the table on the experiment group detail page. */
  'experiments.group.afterSearch': {
    workspace: string;
    experimentGroupName: string;
    experimentGroupId: string;
    totalCount: number;
    /** The experiment rows currently in the table view (the loaded page, post-search/filter). */
    experiments: readonly ExperimentResponse[];
  };
  /** Above the search bar and filters on the single-experiment detail page. */
  'experiments.detail.beforeSearch': {
    workspace: string;
    experimentGroupName: string;
    experimentName: string;
    totalCount: number;
    /** The test-case sessions currently in the table view (the loaded page, post-search/filter). */
    testCases: readonly ExperimentSessionResponse[];
  };
  /** Between the search bar and the table on the single-experiment detail page. */
  'experiments.detail.afterSearch': {
    workspace: string;
    experimentGroupName: string;
    experimentName: string;
    totalCount: number;
    /** The test-case sessions currently in the table view (the loaded page, post-search/filter). */
    testCases: readonly ExperimentSessionResponse[];
  };
}

export type SlotId = keyof SlotContextMap;

/**
 * The source of truth for view overrides. Each `viewId` maps to the typed context a replacement
 * view receives — workspace, route params, and anything else the host route already resolved.
 */
export interface ViewContextMap {
  /** Full-page trace detail at `/workspaces/:workspace/intake/traces/:traceId`. */
  'intake.trace.detail': {
    workspace: string;
    traceId: string;
  };
}

export type ViewId = keyof ViewContextMap;

/** A plugin-provided replacement for an entire first-party view. */
export interface ViewOverride {
  readonly viewId: ViewId;
  /** Stable, globally-unique id (convention: `<plugin-id>:<name>`). */
  readonly id: string;
  /** Lower wins when multiple plugins target the same view; ties keep manifest order. */
  readonly order: number;
  readonly render: ComponentType<Record<string, unknown>>;
}

/** A single component a plugin renders into a slot, with its identity and ordering metadata. */
export interface SlotContribution {
  readonly slot: SlotId;
  /** Stable, globally-unique id (convention: `<plugin-id>:<name>`). Used as the React key. */
  readonly id: string;
  /** Lower renders first; ties keep manifest order. */
  readonly order: number;
  /**
   * Props-erased component. Authored against a slot's typed context but stored erased so the
   * registry can hold contributions for different slots in one list. Build via `contribute`,
   * which preserves type safety at the authoring site.
   */
  readonly render: ComponentType<Record<string, unknown>>;
}

/**
 * A standalone page a plugin contributes. Registered under the workspace index in `routes/index.tsx`,
 * so `path` is workspace-relative (no leading slash) and may use the same `:param` segments as
 * core routes — e.g. `experiment/:experimentGroupName/:experimentName/errors`.
 */
export interface PluginRoute {
  /** Stable, globally-unique id (convention: `<plugin-id>:<name>`). */
  readonly id: string;
  /** Path under `/workspaces/:workspace/`, no leading slash. Reads params via `useParams`. */
  readonly path: string;
  /** The page component. Statically imported via the manifest, like core routes. */
  readonly render: ComponentType;
}

/** Workspace scope for a plugin manifest entry. */
export type PluginWorkspaceScope = readonly string[] | 'all';

/** One plugin: a named bundle of slot contributions and/or routes, registered in the local manifest. */
export interface StudioPlugin {
  readonly id: string;
  readonly name: string;
  readonly description?: string;
  /**
   * Workspaces where this plugin is active. Defaults to `['default']` when omitted.
   * Use `'all'` to apply in every workspace.
   */
  readonly workspaces?: PluginWorkspaceScope;
  readonly contributions: readonly SlotContribution[];
  /** Standalone pages this plugin adds. Merged into the router behind the plugin flag. */
  readonly routes?: readonly PluginRoute[];
  /** Full-view replacements keyed by `viewId`. Applied at host routes behind the plugin flag. */
  readonly viewOverrides?: readonly ViewOverride[];
}

/**
 * Type-safe builder for a slot contribution. Binds the component's props to the slot's context
 * type, so wiring a component to the wrong slot fails to compile. The single cast to the
 * props-erased `render` type is contained here, behind a checked boundary.
 */
/**
 * Type-safe builder for a view override. Binds the component's props to the view's context type.
 */
export const overrideView = <V extends ViewId>(config: {
  viewId: V;
  id: string;
  order?: number;
  render: ComponentType<ViewContextMap[V]>;
}): ViewOverride => ({
  viewId: config.viewId,
  id: config.id,
  order: config.order ?? 0,
  render: config.render as ComponentType<Record<string, unknown>>,
});

export const contribute = <S extends SlotId>(config: {
  slot: S;
  id: string;
  order?: number;
  render: ComponentType<SlotContextMap[S]>;
}): SlotContribution => ({
  slot: config.slot,
  id: config.id,
  order: config.order ?? 0,
  render: config.render as ComponentType<Record<string, unknown>>,
});
