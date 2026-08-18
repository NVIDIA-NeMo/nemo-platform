<!-- SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# useDeferredUnmount

A React hook for managing deferred unmounting of panels, modals, sheets, or any component where you need content to persist during exit animations.

## The Problem

When closing a panel that displays dynamic content, the content typically disappears immediately when you set the state to "closed". This causes an abrupt visual experience where the exit animation plays on an empty panel.

```tsx
// ❌ Problem: content disappears before animation completes
const [selectedItem, setSelectedItem] = useState<Item | null>(null);
const isOpen = selectedItem !== null;

<Sheet open={isOpen} onOpenChange={(open) => !open && setSelectedItem(null)}>
  {selectedItem && <ItemDetails item={selectedItem} />}
</Sheet>;
```

## The Solution

`useDeferredUnmount` keeps the value available during a configurable delay period, allowing exit animations to complete smoothly before the content is cleared.

```tsx
// ✅ Solution: content persists during exit animation
const { isOpen, value, open, close } = useDeferredUnmount<Item>();

<Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
  {value && <ItemDetails item={value} />}
</Sheet>;
```

## Installation

This hook is part of `@nemo/common`:

```tsx
import { useDeferredUnmount } from '@nemo/common/hooks/useDeferredUnmount';
```

## API

### Options

| Option  | Type     | Default | Description                                    |
| ------- | -------- | ------- | ---------------------------------------------- |
| `delay` | `number` | `300`   | Milliseconds to wait before clearing the value |

### Return Value

| Property       | Type                      | Description                                         |
| -------------- | ------------------------- | --------------------------------------------------- |
| `isOpen`       | `boolean`                 | Whether the panel is in the "open" state            |
| `value`        | `T \| null`               | The current value (persists during close animation) |
| `open`         | `(value: T) => void`      | Opens the panel with a specific value               |
| `close`        | `() => void`              | Closes the panel (value clears after delay)         |
| `onOpenChange` | `(open: boolean) => void` | Handler for controlled components                   |

## Usage Examples

### Basic Usage with KUI Sheet

```tsx
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@kui/react';
import { useDeferredUnmount } from '@nemo/common/hooks/useDeferredUnmount';

interface Thread {
  id: string;
  title: string;
  messages: Message[];
}

function ThreadPanel() {
  const { isOpen, value: thread, open, close } = useDeferredUnmount<Thread>();

  return (
    <>
      <ThreadList onSelectThread={open} />

      <Sheet open={isOpen} onOpenChange={(open) => !open && close()}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>{thread?.title ?? 'Loading...'}</SheetTitle>
          </SheetHeader>
          {thread && <ThreadDetails thread={thread} />}
        </SheetContent>
      </Sheet>
    </>
  );
}
```

### Using onOpenChange for Controlled Components

The `onOpenChange` callback simplifies integration with controlled components:

```tsx
function DetailPanel() {
  const panel = useDeferredUnmount<string>({ delay: 400 });

  return (
    <Sheet open={panel.isOpen} onOpenChange={panel.onOpenChange}>
      <SheetContent>{panel.value && <Details id={panel.value} />}</SheetContent>
    </Sheet>
  );
}
```

### With Custom Delay

Match the delay to your CSS transition duration:

```tsx
// For a slower 500ms exit animation
const { isOpen, value, open, close } = useDeferredUnmount<Item>({
  delay: 500,
});
```

### Opening with Different Values

The hook handles rapid open/close cycles gracefully:

```tsx
function ItemList({ items }: { items: Item[] }) {
  const { isOpen, value, open, onOpenChange } = useDeferredUnmount<Item>();

  return (
    <>
      {items.map((item) => (
        <ListItem
          key={item.id}
          onClick={() => open(item)} // Can open with different items
        />
      ))}

      <Sheet open={isOpen} onOpenChange={onOpenChange}>
        <SheetContent>{value && <ItemDetails item={value} />}</SheetContent>
      </Sheet>
    </>
  );
}
```

## How It Works

1. **Opening**: When `open(value)` is called, the value is set immediately and `isOpen` becomes `true`
2. **Closing**: When `close()` is called, `isOpen` becomes `false` immediately, but the value persists
3. **Delayed cleanup**: After the delay period, the value is set to `null`
4. **Rapid interactions**: If `open()` is called while a close timeout is pending, the timeout is cancelled

This ensures the content remains visible during the exit animation, then cleans up afterward.

## Best Practices

1. **Match delay to animation duration**: Set the delay to match or slightly exceed your CSS transition duration
2. **Always check for null**: Render content conditionally based on `value` being non-null
3. **Use onOpenChange for controlled components**: It handles both open and close actions appropriately
4. **Don't call open() without a value in onOpenChange**: The `onOpenChange(true)` path only sets `isOpen`, it doesn't set a value
