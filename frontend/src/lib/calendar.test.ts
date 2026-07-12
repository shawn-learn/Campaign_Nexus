import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { CalendarMath } from './calendar'
import type { CalendarDef } from './calendar'

// Parity gate: the TS port must reproduce the Python reference's golden fixtures exactly
// (docs/07, §9.8). The fixtures are self-contained (each carries its calendar def).
const goldenPath = fileURLToPath(
  new URL('../../../backend/tests/fixtures/calendar_golden.json', import.meta.url),
)
interface GoldenCase {
  calendar: CalendarDef
  seconds: number
  parts: Record<string, unknown>
  formatted: Record<string, unknown>
}
const golden: GoldenCase[] = JSON.parse(readFileSync(goldenPath, 'utf-8'))

describe('CalendarMath TS ↔ Python parity', () => {
  it('reproduces every golden case', () => {
    for (const c of golden) {
      const cal = new CalendarMath(c.calendar)
      expect(cal.toParts(c.seconds)).toEqual(c.parts)
      expect({ ...cal.format(c.seconds) }).toEqual(c.formatted)
    }
  })

  it('epoch anchor', () => {
    const cal = new CalendarMath(golden.find((c) => c.seconds === 0)!.calendar)
    expect(cal.format(0).label).toBe('January 1, 1 CE')
    expect(cal.format(0).time).toBe('00:00:00')
  })

  it('fromParts is the inverse of toParts (round-trip)', () => {
    const cal = new CalendarMath(golden.find((c) => c.seconds === 0)!.calendar)
    for (const s of [0, 1, 59, 3600, 86400, 123456789, -1, -86401, 999999999, -500000]) {
      const p = cal.toParts(s)
      expect(cal.fromParts(p.year, p.month_index, p.day_of_month, p.hour, p.minute, p.second)).toBe(s)
    }
  })
})
