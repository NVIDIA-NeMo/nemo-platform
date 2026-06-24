// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { buildQueries, Matcher } from '@testing-library/react';

/** Lucide icons render as `<svg class="lucide lucide-{name}">`. Use the kebab-case suffix (e.g. `cog`, `refresh-cw`). */
const lucideIconSelector = (iconName: string) => `svg.lucide-${iconName}`;

/** Returns all matching Lucide SVGs under `container` (defaults to `document.body`). */
export const queryAllLucideIcons = (
  iconName: string,
  container: ParentNode = document.body
): SVGElement[] => {
  return [...container.querySelectorAll(lucideIconSelector(iconName))] as SVGElement[];
};

const getMultipleError = (_container: Element | null, iconName: string) =>
  `Found multiple lucide icons matching: ${iconName}`;
const getMissingError = (_container: Element | null, iconName: string) =>
  `Unable to find lucide icon: ${iconName}`;

/** Finds a single Lucide icon by kebab-case name, optionally scoped to a container. */
export const getLucideIcon = (
  iconName: string,
  container: ParentNode = document.body
): SVGElement => {
  const icons = queryAllLucideIcons(iconName, container);
  if (icons.length === 0) {
    throw new Error(getMissingError(null, iconName));
  }
  if (icons.length > 1) {
    throw new Error(getMultipleError(null, iconName));
  }
  return icons[0];
};

/** Returns the first matching Lucide icon, or null if none. */
export const queryLucideIcon = (
  iconName: string,
  container: ParentNode = document.body
): SVGElement | null => queryAllLucideIcons(iconName, container)[0] ?? null;

const queryAllByLucideIcon = (container: HTMLElement, iconName: Matcher) => {
  if (typeof iconName !== 'string') {
    throw new TypeError(`Lucide icon name must be a string, received ${typeof iconName}`);
  }
  return queryAllLucideIcons(iconName, container) as unknown as HTMLElement[];
};

export const [
  queryByLucideIcon,
  getAllByLucideIcon,
  getByLucideIcon,
  findAllByLucideIcon,
  findByLucideIcon,
] = buildQueries(queryAllByLucideIcon, getMultipleError, getMissingError);
