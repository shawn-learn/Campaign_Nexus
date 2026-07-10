import { useMemo } from 'react'
import { useClock } from '../api/hooks'
import { CalendarMath } from './calendar'
import type { CalendarDef } from './calendar'

// Builds a CalendarMath from the campaign's calendar (served by the clock endpoint) so
// the UI can format any campaign time locally — no round-trip per timeline row.
export function useCalendar(campaignId: string | null): CalendarMath | null {
  const { data: clock } = useClock(campaignId)
  return useMemo(
    () => (clock ? new CalendarMath(clock.calendar as unknown as CalendarDef) : null),
    [clock],
  )
}
