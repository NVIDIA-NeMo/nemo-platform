// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { ToastProvider } from '@nemo/common/src/providers/toast/ToastProvider';
import { MessageFnOptions, NotifyFn } from '@nemo/common/src/providers/toast/types';
import { useNotify } from '@nemo/common/src/providers/toast/useNotify';
import { logger } from '@nemo/common/src/utils/logger';
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FC } from 'react';

const Notifier: FC<{ onNotify?: NotifyFn; options?: MessageFnOptions }> = ({
  onNotify,
  options,
}) => {
  const notify = useNotify(onNotify);
  return <button onClick={() => notify('All done', 'success', options)}>Notify</button>;
};

describe('useNotify', () => {
  const user = userEvent.setup();

  it('sends to the surrounding ToastProvider when no onNotify is given', async () => {
    render(
      <ToastProvider>
        <Notifier />
      </ToastProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Notify' }));

    expect(await screen.findByText('All done')).toBeInTheDocument();
  });

  it('prefers onNotify over the provider', async () => {
    const onNotify = vi.fn();
    render(
      <ToastProvider>
        <Notifier onNotify={onNotify} />
      </ToastProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Notify' }));

    expect(onNotify).toHaveBeenCalledWith('All done', 'success', undefined);
    expect(screen.queryByText('All done')).not.toBeInTheDocument();
  });

  it('works without a provider, which is the plugin case', async () => {
    const onNotify = vi.fn();
    render(<Notifier onNotify={onNotify} />);

    await user.click(screen.getByRole('button', { name: 'Notify' }));

    expect(onNotify).toHaveBeenCalledWith('All done', 'success', undefined);
  });

  it('forwards toast options to onNotify', async () => {
    const onNotify = vi.fn();
    render(<Notifier onNotify={onNotify} options={{ durationMs: false }} />);

    await user.click(screen.getByRole('button', { name: 'Notify' }));

    expect(onNotify).toHaveBeenCalledWith('All done', 'success', { durationMs: false });
  });

  it('honours durationMs on the provider path', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(
      <ToastProvider>
        <Notifier options={{ durationMs: 60_000 }} />
      </ToastProvider>
    );

    await user.click(screen.getByRole('button', { name: 'Notify' }));
    expect(await screen.findByText('All done')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(10_000);
    });
    expect(screen.getByText('All done')).toBeInTheDocument();

    vi.useRealTimers();
  });

  it('drops the message with a warning when there is no sink at all', async () => {
    const warn = vi.spyOn(logger, 'warn').mockImplementation(() => {});
    render(<Notifier />);

    await user.click(screen.getByRole('button', { name: 'Notify' }));

    expect(warn).toHaveBeenCalledWith(expect.stringContaining('All done'));
    warn.mockRestore();
  });
});
