import { useEffect, useState } from 'react'

// Returns `value` delayed by `delayMs`, so keystroke-driven state (e.g. a search box) can
// throttle the queries/effects it feeds without each character firing a request.
export function useDebounced<T>(value: T, delayMs = 200): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(id)
  }, [value, delayMs])
  return debounced
}
