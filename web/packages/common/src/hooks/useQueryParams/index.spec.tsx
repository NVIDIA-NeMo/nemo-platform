// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { renderHook, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { useQueryParams } from './index';

// Mock react-router-dom
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('useQueryParams', () => {
  beforeEach(() => {
    mockNavigate.mockClear();
  });

  describe('getQueryParams', () => {
    it('should return URLSearchParams object', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });
      const params = result.current.getQueryParams();

      expect(params).toBeInstanceOf(URLSearchParams);
      expect(params.get('page')).toBe('1');
      expect(params.get('sort')).toBe('name');
    });

    it('should return empty URLSearchParams when no query params', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });
      const params = result.current.getQueryParams();

      expect(params.toString()).toBe('');
    });
  });

  describe('getQueryParam', () => {
    it('should get a specific query parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?userId=123']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });
      const userId = result.current.getQueryParam('userId');

      expect(userId).toBe('123');
    });

    it('should return empty string for non-existent parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });
      const missing = result.current.getQueryParam('missing');

      expect(missing).toBe('');
    });

    it('should decode URL-encoded values', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?name=John%20Doe']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });
      const name = result.current.getQueryParam('name');

      expect(name).toBe('John Doe');
    });
  });

  describe('setQueryParam', () => {
    it('should set a single query parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParam('page', '2');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=2');
    });

    it('should update an existing query parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParam('page', '2');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&sort=name');
    });

    it('should delete parameter when value is empty string', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParam('page', '');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?sort=name');
    });

    it('should preserve pathname', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/projects/123?page=1']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParam('page', '2');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/projects/123?page=2');
    });
  });

  describe('setQueryParams', () => {
    it('should set multiple query parameters atomically', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2',
          sort: 'name',
          filter: 'active',
        });
      });

      expect(mockNavigate).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&sort=name&filter=active');
    });

    it('should update and add parameters together', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&existing=true']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2',
          newParam: 'value',
        });
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&existing=true&newParam=value');
    });

    it('should delete parameters with undefined value', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name&filter=active']}>
          {children}
        </MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2',
          filter: undefined,
        });
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&sort=name');
    });

    it('should delete parameters with empty string value', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2',
          sort: '',
        });
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=2');
    });

    it('should handle mixed operations in single call', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name&filter=old&keep=true']}>
          {children}
        </MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2', // update
          sort: undefined, // delete
          filter: 'new', // update
          newParam: 'added', // add
          // keep is not mentioned, so it stays
        });
      });

      expect(mockNavigate).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&filter=new&keep=true&newParam=added');
    });

    it('should preserve pathname with complex path', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/projects/abc-123/evaluation/details?page=1']}>
          {children}
        </MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.setQueryParams({
          page: '2',
          compare: 'eval-456',
        });
      });

      expect(mockNavigate).toHaveBeenCalledWith(
        '/projects/abc-123/evaluation/details?page=2&compare=eval-456'
      );
    });
  });

  describe('removeQueryParam', () => {
    it('should remove a specific query parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&sort=name']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.removeQueryParam('page');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?sort=name');
    });

    it('should handle removing non-existent parameter', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.removeQueryParam('missing');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?page=1');
    });

    it('should result in empty query string when removing last param', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      act(() => {
        result.current.removeQueryParam('page');
      });

      expect(mockNavigate).toHaveBeenCalledWith('/?');
    });
  });

  describe('real-world scenarios', () => {
    it('should handle pagination scenario', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/?page=1&page_size=20']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      // User changes page
      act(() => {
        result.current.setQueryParam('page', '2');
      });
      expect(mockNavigate).toHaveBeenCalledWith('/?page=2&page_size=20');

      mockNavigate.mockClear();

      // User changes page size (should reset to page 1)
      act(() => {
        result.current.setQueryParams({ page: '1', page_size: '50' });
      });
      expect(mockNavigate).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledWith('/?page=1&page_size=50');
    });

    it('should handle comparison scenario', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <MemoryRouter initialEntries={['/evaluation/details/eval-123']}>{children}</MemoryRouter>
      );

      const { result } = renderHook(() => useQueryParams(), { wrapper });

      // Add first comparison
      act(() => {
        result.current.setQueryParams({
          compare: 'eval-456',
          baseline: '0',
        });
      });
      expect(mockNavigate).toHaveBeenCalledWith(
        '/evaluation/details/eval-123?compare=eval-456&baseline=0'
      );

      mockNavigate.mockClear();

      // Add second comparison
      act(() => {
        result.current.setQueryParams({
          compare: 'eval-456,eval-789',
          baseline: '0',
        });
      });
      expect(mockNavigate).toHaveBeenCalledTimes(1);
    });
  });
});
