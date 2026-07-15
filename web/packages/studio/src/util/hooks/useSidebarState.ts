// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useLocalStorage } from '@studio/util/hooks/useLocalStorage';
import { SIDE_NAV_OPEN_KEY } from '@studio/util/localStorage';
import { useCallback, useEffect, useRef } from 'react';

/**
 * Manages sidebar open/collapsed state with responsive behavior.
 *
 * - Persists the state in localStorage.
 * - Auto-collapses when the viewport is narrower than `--breakpoint-md`.
 * - Auto-expands when the viewport widens past the breakpoint.
 * - Skips one auto-change after a manual toggle to respect user intent.
 */
export const useSidebarState = (defaultExpanded = true) => {
  const [navOpen, setNavOpen] = useLocalStorage(
    SIDE_NAV_OPEN_KEY,
    defaultExpanded ? 'true' : 'false'
  );
  const expanded = navOpen === 'true';
  const lastSetByRef = useRef<'auto' | 'manual'>('auto');

  useEffect(() => {
    const mdBreakpoint = getComputedStyle(document.documentElement)
      .getPropertyValue('--breakpoint-md')
      .trim();

    if (!mdBreakpoint) return;

    const mql = window.matchMedia(`(min-width: ${mdBreakpoint})`);

    if (!mql.matches) {
      setNavOpen('false');
    }

    const handleChange = (e: MediaQueryListEvent) => {
      if (lastSetByRef.current === 'manual') {
        lastSetByRef.current = 'auto';
        return;
      }
      setNavOpen(e.matches ? 'true' : 'false');
    };

    mql.addEventListener('change', handleChange);
    return () => mql.removeEventListener('change', handleChange);
  }, [setNavOpen]);

  const toggle = useCallback(() => {
    lastSetByRef.current = 'manual';
    setNavOpen(expanded ? 'false' : 'true');
  }, [expanded, setNavOpen]);

  return { expanded, toggle };
};
