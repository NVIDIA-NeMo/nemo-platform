// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { useLocation, useNavigate } from 'react-router';

/**
 * A hook for managing URL query parameters with React Router.
 * Provides utilities to read, set, and remove query parameters.
 *
 * @example
 * const { getQueryParam, setQueryParam, setQueryParams } = useQueryParams();
 *
 * // Get a single param
 * const userId = getQueryParam('userId');
 *
 * // Set a single param
 * setQueryParam('page', '2');
 *
 * // Set multiple params atomically (single navigation)
 * setQueryParams({ page: '2', sort: 'name' });
 */
export const useQueryParams = () => {
  const location = useLocation();
  const navigate = useNavigate();

  /**
   * Get all current search parameters as URLSearchParams object
   */
  const getQueryParams = () => {
    return new URLSearchParams(location.search);
  };

  /**
   * Get a specific query parameter by key
   * @param key - The parameter key to retrieve
   * @returns The decoded parameter value or undefined if not found
   */
  const getQueryParam = (key: string) => {
    const params = getQueryParams();
    return decodeURIComponent(params.get(key) ?? '') ?? undefined;
  };

  /**
   * Set a single query parameter
   * @param key - The parameter key to set
   * @param value - The parameter value (will be deleted if empty string)
   */
  const setQueryParam = (key: string, value: string) => {
    const params = getQueryParams();
    if (value) {
      params.set(key, value);
    } else {
      params.delete(key);
    }
    navigate(`${location.pathname}?${params.toString()}`);
  };

  /**
   * Set multiple query parameters atomically (single navigation)
   * @param updates - Object of key-value pairs to set/delete
   * @example
   * setQueryParams({ page: '2', sort: 'name', filter: undefined })
   * // Sets page=2, sort=name, and removes filter
   */
  const setQueryParams = (updates: Record<string, string | undefined>) => {
    const params = getQueryParams();
    Object.entries(updates).forEach(([key, value]) => {
      if (value !== undefined && value !== '') {
        params.set(key, value);
      } else {
        params.delete(key);
      }
    });
    navigate(`${location.pathname}?${params.toString()}`);
  };

  /**
   * Remove a query parameter by key
   * @param key - The parameter key to remove
   */
  const removeQueryParam = (key: string) => {
    const params = getQueryParams();
    params.delete(key);
    navigate(`${location.pathname}?${params.toString()}`);
  };

  return {
    getQueryParams,
    getQueryParam,
    setQueryParam,
    setQueryParams,
    removeQueryParam,
  };
};
