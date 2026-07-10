import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { fold } from './combatReducer'
import type { Action } from './combatReducer'

// Parity gate: the TS combat reducer must reproduce the Python reference's golden fixtures
// exactly (ADR-005), so the optimistic UI never disagrees with the server's fold.
const goldenPath = fileURLToPath(
  new URL('../../../backend/tests/fixtures/combat_golden.json', import.meta.url),
)
interface GoldenCase {
  name: string
  actions: Action[]
  expected: Record<string, unknown>
}
const golden: GoldenCase[] = JSON.parse(readFileSync(goldenPath, 'utf-8'))

describe('combat reducer TS ↔ Python parity', () => {
  for (const c of golden) {
    it(c.name, () => {
      expect(fold(c.actions)).toEqual(c.expected)
    })
  }
})
