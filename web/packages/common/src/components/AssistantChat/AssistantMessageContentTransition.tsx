// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { type ReactNode, useEffect, useRef } from 'react';

const COMPLETION_ANIMATION_DURATION_MS = 450;
const MINIMUM_COLLAPSE_HEIGHT_PX = 8;

interface AssistantMessageContentTransitionProps {
  readonly children: ReactNode;
  readonly completed: boolean;
  readonly enabled: boolean;
}

export const AssistantMessageContentTransition = ({
  children,
  completed,
  enabled,
}: AssistantMessageContentTransitionProps) => {
  const contentRef = useRef<HTMLDivElement>(null);
  const previousHeightRef = useRef<number | undefined>(undefined);
  const animationRef = useRef<Animation | undefined>(undefined);
  const completedRef = useRef(completed);
  const enabledRef = useRef(enabled);
  completedRef.current = completed;
  enabledRef.current = enabled;

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === 'undefined') return undefined;

    const observer = new ResizeObserver(([entry]) => {
      if (!entry || animationRef.current) return;

      const previousHeight = previousHeightRef.current;
      const nextHeight = entry.contentRect.height;
      previousHeightRef.current = nextHeight;
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (
        !enabledRef.current ||
        !completedRef.current ||
        reduceMotion ||
        previousHeight === undefined ||
        previousHeight - nextHeight < MINIMUM_COLLAPSE_HEIGHT_PX ||
        typeof content.animate !== 'function'
      ) {
        return;
      }

      content.style.overflow = 'hidden';
      const animation = content.animate(
        [
          { height: `${previousHeight}px`, opacity: 0.72 },
          { height: `${nextHeight}px`, opacity: 1 },
        ],
        {
          duration: COMPLETION_ANIMATION_DURATION_MS,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        }
      );
      animationRef.current = animation;

      const finishAnimation = () => {
        content.style.overflow = '';
        animationRef.current = undefined;
      };
      animation.onfinish = finishAnimation;
      animation.oncancel = finishAnimation;
    });
    observer.observe(content);

    return () => {
      observer.disconnect();
      animationRef.current?.cancel();
    };
  }, []);

  return (
    <div ref={contentRef} className="w-full" data-testid="assistant-message-content-transition">
      {children}
    </div>
  );
};
