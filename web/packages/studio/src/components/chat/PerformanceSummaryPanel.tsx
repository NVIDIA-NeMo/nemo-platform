// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Text } from '@nvidia/foundations-react-core';
import {
  CROWN_COLOR_CLASS,
  MetricValue,
  WINNER_ROWS,
  type Winners,
  type WinnerStats,
} from '@studio/components/chat/BestPerformingSummary';
import {
  PANEL_ROLE_COLORS,
  PANEL_ROLE_DOT_CLASS,
  PANEL_ROLE_LABELS,
} from '@studio/routes/ModelCompareRoute/types';
import { ChevronDown, ChevronUp, Crown } from 'lucide-react';
import { type FC } from 'react';

/** Per-model average stats plus the number of turns they were averaged over. */
export type PanelAverage = (WinnerStats & { count: number }) | null;

interface PerformanceSummaryPanelProps {
  /** Comparison panels, in display order. */
  models: { id: number }[];
  /** Per-panel average across all turns (null when the panel has no results). */
  averagesById: Record<number, PanelAverage>;
  /** Overall winners across the session, or null when fewer than two panels have results. */
  winners: Winners | null;
  /** Resolves a panel id to a model display label. */
  modelLabelById: (id: number) => string;
  expanded: boolean;
  onToggleExpanded: () => void;
  /** When true, reserve the trailing "+" add-panel slot on the right so the
   *  boxes line up under their chat panels (which leave room for that button). */
  reserveTrailingSlot?: boolean;
  /** Callback ref for the horizontal scroll row, used to sync scroll with the
   *  chat-panel row above so the columns track together. */
  scrollRef?: (el: HTMLElement | null) => void;
}

/** Position-based role for a panel index (same clamp rule the chat grid uses). */
const roleForIndex = (idx: number) =>
  PANEL_ROLE_COLORS[Math.min(idx, PANEL_ROLE_COLORS.length - 1)];

// Fixed cell heights so each metric row lines up across the separate boxes.
const HEADER_CELL = 'flex h-10 items-center px-3';
const METRIC_CELL = 'flex h-9 items-center px-3';
const BOX =
  'min-w-[360px] flex-1 overflow-hidden rounded-lg border border-base bg-surface-raised';

/**
 * Colored dot + label, matching the chat panel headers. The dot color is keyed
 * to the panel role (Baseline/Comparison N); `label` overrides the text (e.g.
 * "Average") and defaults to the role name when omitted.
 */
const RoleBadge: FC<{ index: number; title?: string; label?: string }> = ({
  index,
  title,
  label,
}) => {
  const role = roleForIndex(index);
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5" title={title}>
      <span className={`h-2 w-2 shrink-0 rounded-full ${PANEL_ROLE_DOT_CLASS[role]}`} />
      <span className="truncate">
        <Text kind="label/semibold/sm">{label ?? PANEL_ROLE_LABELS[role]}</Text>
      </span>
    </span>
  );
};

/** A single averaged metric value (or em-dash when the panel has no turns). */
const MetricCell: FC<{ avg: PanelAverage; metricKey: keyof Winners; isWinner: boolean }> = ({
  avg,
  metricKey,
  isWinner,
}) => (
  <div className={METRIC_CELL}>
    {avg ? (
      <MetricValue stats={avg} metricKey={metricKey} highlight={isWinner} />
    ) : (
      <Text kind="body/regular/md" className="text-fg-subdued">
        —
      </Text>
    )}
  </div>
);

/**
 * Compare-tab performance summary. Renders one box per chat panel so the boxes
 * line up under their panels above: the first box (Baseline) is split into a
 * "Best Performing" digest and the Baseline averages; each comparison box shows
 * that model's averages, brand green on the metric it wins. Aggregates across
 * all multi-turn turns.
 */
export const PerformanceSummaryPanel: FC<PerformanceSummaryPanelProps> = ({
  models,
  averagesById,
  winners,
  modelLabelById,
  expanded,
  onToggleExpanded,
  reserveTrailingSlot = false,
  scrollRef,
}) => {
  if (models.length === 0) return null;
  const baseline = models[0];
  const comparisons = models.slice(1);
  // With only the baseline (no comparison columns) the left digest header's
  // "Average" label is redundant with the baseline column's own "Average"
  // badge, so we drop it for the single-baseline case.
  const isSingleBaseline = comparisons.length === 0;
  // Resolve a winning panel id back to its column index for role identity.
  const idToIndex = new Map(models.map((m, idx) => [m.id, idx]));

  return (
    // `gap-3`, the `min-w-[360px]` boxes, `overflow-x-auto`, and the trailing w-8
    // spacer mirror the chat row's flex layout so the boxes align under their panels.
    // `scrollRef` syncs this row's horizontal scroll with the chat row above.
    <div ref={scrollRef} className="flex gap-3 overflow-x-auto">
      {/* Baseline box: Best Performing digest | Baseline averages. */}
      <div className={BOX}>
        <div
          className="grid"
          style={{
            // eslint-disable-next-line no-restricted-syntax -- two-up split inside one panel width
            gridTemplateColumns: 'minmax(0, 1.2fr) minmax(0, 1fr)',
          }}
        >
          {/* Best Performing (collapsible) */}
          <div className="flex flex-col border-r border-base">
            <div className={HEADER_CELL}>
              <button
                type="button"
                onClick={onToggleExpanded}
                className="flex w-full cursor-pointer items-center justify-between gap-1.5"
                aria-expanded={expanded}
              >
                <span className="inline-flex min-w-0 items-center gap-1.5">
                  {!isSingleBaseline && (
                    <Crown size={14} className={`shrink-0 ${CROWN_COLOR_CLASS}`} />
                  )}
                  <span className="truncate">
                    <Text kind="label/semibold/sm">
                      {isSingleBaseline ? '' : 'Best Performing'}
                    </Text>
                  </span>
                </span>
                {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>
            </div>
            {expanded &&
              WINNER_ROWS.map(({ key, label }) => (
                <div key={key} className={`${METRIC_CELL} justify-between gap-2`}>
                  <Text kind="body/regular/sm" className="truncate text-fg-subdued">
                    {label}
                  </Text>
                  {winners && (
                    <span className="inline-flex min-w-0 items-center gap-1">
                      <RoleBadge
                        index={idToIndex.get(winners[key]) ?? 0}
                        title={modelLabelById(winners[key])}
                      />
                    </span>
                  )}
                </div>
              ))}
          </div>

          {/* Baseline averages */}
          <div className="flex flex-col">
            <div className={HEADER_CELL}>
              <RoleBadge index={0} title={modelLabelById(baseline.id)} label="Average" />
            </div>
            {expanded &&
              WINNER_ROWS.map(({ key }) => (
                <MetricCell
                  key={key}
                  avg={averagesById[baseline.id]}
                  metricKey={key}
                  isWinner={winners ? winners[key] === baseline.id : false}
                />
              ))}
          </div>
        </div>
      </div>

      {/* One box per comparison, aligned under its chat panel. */}
      {comparisons.map((m, i) => {
        const idx = i + 1;
        return (
          <div key={m.id} className={BOX}>
            <div className="flex flex-col">
              <div className={HEADER_CELL}>
                <RoleBadge index={idx} title={modelLabelById(m.id)} label="Average" />
              </div>
              {expanded &&
                WINNER_ROWS.map(({ key }) => (
                  <MetricCell
                    key={key}
                    avg={averagesById[m.id]}
                    metricKey={key}
                    isWinner={winners ? winners[key] === m.id : false}
                  />
                ))}
            </div>
          </div>
        );
      })}

      {/* Matches the chat row's trailing "+" add-panel button so boxes align. */}
      {reserveTrailingSlot && <div className="h-0 w-8 shrink-0" aria-hidden />}
    </div>
  );
};
