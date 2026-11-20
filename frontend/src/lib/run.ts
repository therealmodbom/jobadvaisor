import { useEffect, useState } from 'react'

/** How often a computing scoring pass or availability check is polled, in milliseconds. */
export const POLL_MS = 1000
/** Failed polls in a row after which polling stops and a retry is offered. */
export const POLL_FAILURES = 3
/** How long a button that just appeared after a swap ignores presses, in milliseconds. */
export const SWAP_LOCK_MS = 1000

/** The swap lock and focus hand-off of a start button that gives way to its cancel button
 * (`working` true) and back, shared by the pass and the check. `area` is the CSS selector of the
 * element that marks the focus area of the button. For `SWAP_LOCK_MS` after each swap `locked` is
 * true, so a double click cannot cancel what it just started nor a late cancel click start anew.
 * `handoff` is true when focus was inside `area` before the swap (read at render time, before the
 * commit: Chromium blurs a focused button that turns inert), and `seenWorking` is the state the
 * swap went to, for the layout effect that moves focus. */
export function useSwapLock(working: boolean, area: string) {
  const [seenWorking, setSeenWorking] = useState(working)
  const [locked, setLocked] = useState(false)
  const [handoff, setHandoff] = useState(false)
  if (seenWorking !== working) {
    setSeenWorking(working)
    setLocked(true)
    setHandoff(document.activeElement?.closest(area) != null)
  }
  useEffect(() => {
    if (!locked) return
    const timer = setTimeout(() => setLocked(false), SWAP_LOCK_MS)
    return () => clearTimeout(timer)
  }, [locked, seenWorking])
  return { locked, handoff, seenWorking }
}
