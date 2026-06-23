// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { featureFlags } from '@studio/constants/featureFlags';
import { getSlotContributions } from '@studio/plugins/registry';
import type { SlotContextMap, SlotId } from '@studio/plugins/types';

interface PluginSlotProps<S extends SlotId> {
  slot: S;
  /** Typed context passed as props to every component contributed to this slot. */
  context: SlotContextMap[S];
}

/**
 * Renders every plugin contribution registered for `slot`, in order, passing the slot's typed
 * `context` to each. Renders nothing when the experiment-plugins flag is off or no plugin
 * targets the slot — so hosts can drop it into a layout unconditionally.
 */
export const PluginSlot = <S extends SlotId>({ slot, context }: PluginSlotProps<S>) => {
  if (featureFlags.experimentPlugins === false) return null;

  const contributions = getSlotContributions(slot, context.workspace);
  if (contributions.length === 0) return null;

  // Wrap in a content-height flex column so slot content hugs its own height. Hosts often place
  // a slot inside a flex container that fills available space (e.g. the DataView's `flex-1`
  // column), and foundations `Card` defaults to `height: 100%` — without this wrapper a single
  // card would stretch to fill the column, leaving dead space below its content. `shrink-0`
  // keeps it from being compressed when the sibling table claims the remaining height.
  return (
    <div className="flex flex-col gap-density-xl shrink-0">
      {contributions.map(({ id, render: Render }) => (
        // `context` is keyed by the same slot id as the contribution, so its shape always
        // matches the component's props; the registry erases the prop type to hold mixed slots.
        <Render key={id} {...(context as Record<string, unknown>)} />
      ))}
    </div>
  );
};
