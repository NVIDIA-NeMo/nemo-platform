// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { AssistantMessageContentTransition } from '@nemo/common/src/components/AssistantChat/AssistantMessageContentTransition';
import { render } from '@testing-library/react';

const makeMediaQueryList = (matches: boolean): MediaQueryList =>
  ({
    matches,
    media: '(prefers-reduced-motion: reduce)',
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }) as MediaQueryList;

describe('AssistantMessageContentTransition', () => {
  it('animates a completed message from its streamed height to its summary height', () => {
    let onResize: ResizeObserverCallback = () => undefined;
    class ResizeObserverMock {
      constructor(callback: ResizeObserverCallback) {
        onResize = callback;
      }

      disconnect = vi.fn();
      observe = vi.fn();
      unobserve = vi.fn();
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.spyOn(window, 'matchMedia').mockReturnValue(makeMediaQueryList(false));
    const animation = { cancel: vi.fn(), oncancel: null, onfinish: null } as unknown as Animation;
    const animate = vi.fn().mockReturnValue(animation);
    Object.defineProperty(HTMLElement.prototype, 'animate', {
      configurable: true,
      value: animate,
    });

    const { rerender } = render(
      <AssistantMessageContentTransition completed={false} enabled>
        Detailed streamed work
      </AssistantMessageContentTransition>
    );
    onResize([{ contentRect: { height: 400 } } as ResizeObserverEntry], {} as ResizeObserver);

    rerender(
      <AssistantMessageContentTransition completed enabled>
        Short summary
      </AssistantMessageContentTransition>
    );
    onResize([{ contentRect: { height: 120 } } as ResizeObserverEntry], {} as ResizeObserver);

    expect(animate).toHaveBeenCalledWith(
      [
        { height: '400px', opacity: 0.72 },
        { height: '120px', opacity: 1 },
      ],
      {
        duration: 450,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      }
    );
  });
});
