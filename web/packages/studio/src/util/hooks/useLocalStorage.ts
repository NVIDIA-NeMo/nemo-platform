// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useCallback, useRef, useSyncExternalStore } from 'react';

// The browser `storage` event only fires in *other* tabs, so it can't notify the writing tab.
// We dispatch this custom event on every local write to keep the current tab reactive too.
const LOCAL_STORAGE_EVENT = 'nemo-studio:local-storage';

const notify = (key: string) => {
  if (typeof window === 'undefined') {
    return;
  }
  window.dispatchEvent(new CustomEvent(LOCAL_STORAGE_EVENT, { detail: key }));
};

const subscribe = (key: string, callback: () => void) => {
  const onStorage = (e: StorageEvent) => {
    // `e.key` is null when storage is cleared, in which case every key may have changed.
    if (e.key === null || e.key === key) {
      callback();
    }
  };
  const onLocal = (e: Event) => {
    if ((e as CustomEvent<string>).detail === key) {
      callback();
    }
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(LOCAL_STORAGE_EVENT, onLocal);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(LOCAL_STORAGE_EVENT, onLocal);
  };
};

export const useLocalStorage = <T>(key: string, defaultValue?: T) => {
  // Freeze the default to the first render's reference. `useSyncExternalStore` compares snapshots
  // with `Object.is`, so returning a fresh inline default (e.g. `[]`) on every render would loop.
  // This also matches the previous lazy-`useState` semantics, where the default was read once.
  const defaultValueRef = useRef(defaultValue);

  // Cache the parsed value so a snapshot returns a stable reference until the raw string changes.
  const cache = useRef<{ raw: string | null; value: T | undefined }>({
    raw: null,
    value: defaultValueRef.current,
  });

  const getSnapshot = useCallback((): T | undefined => {
    let raw: string | null;
    try {
      raw = window.localStorage.getItem(key);
    } catch {
      return defaultValueRef.current;
    }
    if (raw === null) {
      return defaultValueRef.current;
    }
    if (cache.current.raw === raw) {
      return cache.current.value;
    }
    try {
      const parsed = JSON.parse(raw) as T;
      cache.current = { raw, value: parsed };
      return parsed;
    } catch {
      return defaultValueRef.current;
    }
  }, [key]);

  const getServerSnapshot = useCallback(() => defaultValueRef.current, []);

  const storedValue = useSyncExternalStore(
    useCallback((callback: () => void) => subscribe(key, callback), [key]),
    getSnapshot,
    getServerSnapshot
  );

  const setValue = useCallback(
    (value: T) => {
      try {
        if (typeof window !== 'undefined') {
          window.localStorage.setItem(key, JSON.stringify(value));
          notify(key);
        }
      } catch {
        // do nothing
      }
    },
    [key]
  );

  const deleteValue = useCallback(() => {
    try {
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(key);
        notify(key);
      }
    } catch {
      // do nothing
    }
  }, [key]);

  return [storedValue, setValue, deleteValue] as const;
};
