import { useEffect, useState } from 'react';

/**
 * Rotate through a list of status messages while a long-running op is active.
 * Lets loading states narrate progress instead of a single static label.
 */
export function useRotatingText(messages: readonly string[], active: boolean, intervalMs = 2500): string {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    if (!active || messages.length <= 1) {
      setIdx(0);
      return;
    }
    const timer = setInterval(() => {
      setIdx((i) => (i + 1) % messages.length);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [active, messages.length, intervalMs]);

  return messages[idx] ?? messages[0] ?? '';
}
