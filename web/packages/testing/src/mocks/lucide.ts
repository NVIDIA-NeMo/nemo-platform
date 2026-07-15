// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/*
 * lucide-react mock factory.
 *
 *   vi.mock('lucide-react', async () =>
 *     (await import('@nemo/testing/mocks/lucide')).mockLucideReact(import('react'))
 *   );
 *
 *   // query in a test:
 *   screen.getByTestId('download-icon');
 *   // or, to avoid guessing the kebab-case spelling:
 *   screen.getByTestId(iconTestId('Download'));
 */

/*
 * Minimal slice of the React API this mock needs, supplied by the consumer.
 *
 * The signatures are deliberately the "top function type" (`(...args: never[]) =>
 * unknown`) so the real, heavily-overloaded react module is structurally
 * assignable to this. A precise signature (e.g. `createElement(type: string, ...)`)
 * would NOT accept `typeof import('react')` under strictFunctionTypes, and this
 * package has no @types/react of its own to borrow the real types from. The
 * functions are narrowed to their usable shapes inside `mockLucideReact`.
 */
interface ReactLike {
  createElement: (...args: never[]) => unknown;
  forwardRef: (...args: never[]) => unknown;
}

/** The usable slice of React we narrow to internally, once handed in. */
type CreateElement = (type: string, props?: Record<string, unknown> | null) => unknown;
type ForwardRef = (render: (props: Record<string, unknown>, ref: unknown) => unknown) => {
  (props: Record<string, unknown>): unknown;
  displayName?: string;
};

/** Convert a lucide icon name (PascalCase) to its mock `data-testid`. */
export const iconTestId = (iconName: string): string =>
  `${iconName
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .toLowerCase()}-icon`;

const DOM_SAFE_PROPS = new Set([
  'className',
  'style',
  'id',
  'role',
  'tabIndex',
  'onClick',
  'onMouseEnter',
  'onMouseLeave',
  'onFocus',
  'onBlur',
]);

const pickDomProps = (props: Record<string, unknown>): Record<string, unknown> => {
  const forwarded: Record<string, unknown> = {};
  for (const key of Object.keys(props)) {
    if (DOM_SAFE_PROPS.has(key) || key.startsWith('aria-') || key.startsWith('data-')) {
      forwarded[key] = props[key];
    }
  }
  return forwarded;
};

/**
 * Build a lucide-react module namespace whose every export is a mock icon.
 */
export const mockLucideReact = async (react: ReactLike | Promise<ReactLike>): Promise<unknown> => {
  const resolved = await react;
  // Narrow from the top-function-type accepted at the boundary to the shapes we
  // actually call. Safe: the real react module supplies exactly these functions.
  const createElement = resolved.createElement as CreateElement;
  const forwardRef = resolved.forwardRef as ForwardRef;
  const iconCache = new Map<string, unknown>();

  const makeIcon = (name: string): unknown => {
    const testId = iconTestId(name);
    const Icon = forwardRef((props, ref) =>
      createElement('svg', {
        ref,
        'data-testid': testId,
        ...pickDomProps(props),
      })
    );
    Icon.displayName = name;
    return Icon;
  };

  const namespace: unknown = new Proxy(
    {},
    {
      get(_target, prop) {
        if (prop === '__esModule') return true;
        if (prop === 'default') return namespace;
        if (prop === 'then' || typeof prop === 'symbol') return undefined;

        const name = prop;
        if (!iconCache.has(name)) iconCache.set(name, makeIcon(name));
        return iconCache.get(name);
      },
      has() {
        return true;
      },
    }
  );
  return namespace;
};
