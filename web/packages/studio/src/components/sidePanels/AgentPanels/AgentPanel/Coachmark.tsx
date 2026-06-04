// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { Button } from '@nvidia/foundations-react-core';
import { TourCard } from '@studio/components/WelcomeTour/TourCard';
import type { TooltipCoords } from '@studio/components/WelcomeTour/types';
import { computePosition } from '@studio/components/WelcomeTour/utils';
import type { TooltipPosition } from 'modern-tour';
import {
  type FC,
  type RefObject,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';

interface CoachmarkProps {
  targetRef: RefObject<HTMLElement | null>;
  title: string;
  body: string;
  placement?: TooltipPosition;
  /** Optional CTA shown alongside dismiss (e.g. the final "Got it"). */
  primaryLabel?: string;
  onPrimary?: () => void;
  onDismiss: () => void;
  stepLabel?: string;
}

export const Coachmark: FC<CoachmarkProps> = ({
  targetRef,
  title,
  body,
  placement = 'left',
  primaryLabel,
  onPrimary,
  onDismiss,
  stepLabel,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [coords, setCoords] = useState<TooltipCoords | null>(null);

  const reposition = useCallback(() => {
    const target = targetRef.current;
    const card = cardRef.current;
    if (!target || !card) return;
    setCoords(
      computePosition(target.getBoundingClientRect(), card.getBoundingClientRect(), placement)
    );
  }, [targetRef, placement]);

  // The modal SidePanel is a native <dialog> in the browser top layer, which
  // sits above every z-index. Promote the card into the top layer too via the
  // Popover API (manual = no backdrop/light-dismiss) so it paints above the
  // panel. Must open before measuring — a closed popover is display:none.
  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    try {
      el.showPopover();
    } catch {
      // Popover API unsupported (or already open) — falls back to the z-index below.
    }
    return () => {
      try {
        el.hidePopover();
      } catch {
        /* already hidden */
      }
    };
  }, []);

  useLayoutEffect(reposition, [reposition, title, body]);

  // Track the target instead of polling: reflows that resize the target or the
  // card, viewport resizes, and ancestor scrolls all trigger a reposition.
  useEffect(() => {
    reposition();
    const observer =
      typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => reposition()) : null;
    if (observer) {
      if (targetRef.current) observer.observe(targetRef.current);
      if (cardRef.current) observer.observe(cardRef.current);
    }
    window.addEventListener('resize', reposition);
    window.addEventListener('scroll', reposition, true); // capture → any ancestor scroll
    return () => {
      observer?.disconnect();
      window.removeEventListener('resize', reposition);
      window.removeEventListener('scroll', reposition, true);
    };
  }, [reposition, targetRef]);

  // Rendered inside the SidePanel's <dialog> subtree (not portaled to body) so
  // the panel's outside-click-to-close treats clicks here as "inside" and
  // doesn't dismiss. The Popover API still lifts it into the top layer, so it
  // paints above the modal and escapes the panel's clipping/transform.
  return (
    <div
      ref={cardRef}
      popover="manual"
      role="dialog"
      aria-label={title}
      className={`pointer-events-auto fixed inset-auto z-[10001] m-0 w-[340px] max-w-[calc(100vw-32px)] overflow-visible bg-transparent p-0 ${
        coords ? '' : 'invisible'
      }`}
      style={coords ? { left: coords.left, top: coords.top } : undefined} // eslint-disable-line no-restricted-syntax
    >
      <TourCard
        title={title}
        body={body}
        stepLabel={stepLabel}
        closeLabel="Dismiss"
        onClose={onDismiss}
        actions={
          primaryLabel ? (
            <Button kind="primary" color="brand" size="small" onClick={onPrimary ?? onDismiss}>
              {primaryLabel}
            </Button>
          ) : (
            <Button kind="tertiary" color="neutral" size="small" onClick={onDismiss}>
              Skip
            </Button>
          )
        }
      />
    </div>
  );
};
