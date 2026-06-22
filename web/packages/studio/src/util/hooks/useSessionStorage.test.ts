// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useSessionStorage } from '@studio/util/hooks/useSessionStorage';
import { renderHook, act } from '@testing-library/react';

describe('useSessionStorage', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns default value when no stored value exists', () => {
    const { result } = renderHook(() => useSessionStorage('test-key', 'default'));
    expect(result.current[0]).toBe('default');
  });

  it('returns undefined when no default and no stored value', () => {
    const { result } = renderHook(() => useSessionStorage('test-key'));
    expect(result.current[0]).toBeUndefined();
  });

  it('reads existing value from sessionStorage', () => {
    sessionStorage.setItem('test-key', JSON.stringify('stored-value'));
    const { result } = renderHook(() => useSessionStorage('test-key', 'default'));
    expect(result.current[0]).toBe('stored-value');
  });

  it('setValue updates state and sessionStorage', () => {
    const { result } = renderHook(() => useSessionStorage<string>('test-key', 'initial'));

    act(() => {
      result.current[1]('updated');
    });

    expect(result.current[0]).toBe('updated');
    expect(sessionStorage.getItem('test-key')).toBe(JSON.stringify('updated'));
  });

  it('deleteValue removes from state and sessionStorage', () => {
    sessionStorage.setItem('test-key', JSON.stringify('to-delete'));
    const { result } = renderHook(() => useSessionStorage<string>('test-key', 'default'));

    expect(result.current[0]).toBe('to-delete');

    act(() => {
      result.current[2]();
    });

    expect(result.current[0]).toBeUndefined();
    expect(sessionStorage.getItem('test-key')).toBeNull();
  });

  it('handles objects as values', () => {
    const obj = { name: 'test', count: 42 };
    const { result } = renderHook(() => useSessionStorage<typeof obj>('obj-key'));

    act(() => {
      result.current[1](obj);
    });

    expect(result.current[0]).toEqual(obj);
    expect(JSON.parse(sessionStorage.getItem('obj-key')!)).toEqual(obj);
  });

  it('falls back to default when sessionStorage has invalid JSON', () => {
    sessionStorage.setItem('bad-key', 'not-json{');
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // SyntaxError from JSON.parse is caught → returns defaultValue
    const { result } = renderHook(() => useSessionStorage('bad-key', 'fallback'));

    expect(result.current[0]).toBe('fallback');
    spy.mockRestore();
  });
});
