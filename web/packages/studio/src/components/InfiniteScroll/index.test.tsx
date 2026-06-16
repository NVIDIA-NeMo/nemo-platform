// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { InfiniteScroll } from '@studio/components/InfiniteScroll';
import { act, render, screen } from '@testing-library/react';

let mockObserverCallback: ((entries: IntersectionObserverEntry[]) => void) | null = null;

// Vitest 4: constructor mocks must use function/class, not arrow functions
const IntersectionObserverMock = vi.fn(function IntersectionObserverMock(
  callback: (entries: IntersectionObserverEntry[]) => void
) {
  mockObserverCallback = callback;
  return {
    observe: vi.fn(),
    unobserve: vi.fn(),
    disconnect: vi.fn(),
  };
});
vi.stubGlobal('IntersectionObserver', IntersectionObserverMock);

describe('InfiniteScroll', () => {
  afterEach(() => {
    vitest.clearAllMocks();
    mockObserverCallback = null;
  });

  it('renders children and loader when intersecting', async () => {
    const onLoadMore = vitest.fn().mockReturnValue(new Promise(vitest.fn()));

    render(
      <InfiniteScroll hasMore onLoadMore={onLoadMore}>
        <div>Content</div>
      </InfiniteScroll>
    );

    await act(async () => {
      mockObserverCallback!([{ isIntersecting: true } as IntersectionObserverEntry]);
    });
    expect(onLoadMore).toHaveBeenCalledTimes(1);
    expect(await screen.findByTestId('nv-spinner-spinner')).toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });

  it('hides loader and skips onLoadMore when not intersecting', async () => {
    const onLoadMore = vitest.fn().mockReturnValue(new Promise(vitest.fn()));

    render(
      <InfiniteScroll hasMore onLoadMore={onLoadMore}>
        <div>Content</div>
      </InfiniteScroll>
    );

    await act(async () => {
      mockObserverCallback!([{ isIntersecting: false } as IntersectionObserverEntry]);
    });
    expect(onLoadMore).toHaveBeenCalledTimes(0);
    expect(screen.queryByTestId('nv-spinner-spinner')).not.toBeInTheDocument();
    expect(screen.getByText('Content')).toBeInTheDocument();
  });
});
