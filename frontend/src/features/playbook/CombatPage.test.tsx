import { render, cleanup, within, fireEvent, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CombatState } from '../../lib/combatReducer'

// The reducer twin is unit-tested elsewhere (combatReducer.test.ts); this test covers the
// wiring the page adds on top: hook plumbing, the optimistic-then-reconcile action flow,
// and that combat state renders. The API layer and active-campaign hook are mocked so the
// component runs without a backend. Note the first combatant is auto-selected, so its name
// appears twice (initiative rail + detail panel) — assertions target unambiguous text
// ("Serah" is roster-only, the round heading and HP text are unique).
vi.mock('../../shell/useActiveCampaign', () => ({
  useActiveCampaign: () => ({ campaign: { id: 'camp1' }, isLoading: false }),
}))

const startCombat = vi.fn()
const combatAction = vi.fn()
const getCombat = vi.fn()
const combatUndo = vi.fn()
const combatRedo = vi.fn()
const endCombat = vi.fn()

vi.mock('../../api/hooks', () => ({
  useEncounters: () => ({ data: [{ id: 'enc1', name: 'Goblin Ambush' }] }),
  startCombat: (...args: unknown[]) => startCombat(...args),
  combatAction: (...args: unknown[]) => combatAction(...args),
  getCombat: (...args: unknown[]) => getCombat(...args),
  combatUndo: (...args: unknown[]) => combatUndo(...args),
  combatRedo: (...args: unknown[]) => combatRedo(...args),
  endCombat: (...args: unknown[]) => endCombat(...args),
}))

import { CombatPage } from './CombatPage'

function stateWith(round: number, turnIndex: number): CombatState {
  return {
    round,
    turn_index: turnIndex,
    order: ['g1', 's1'],
    combatants: {
      g1: {
        id: 'g1', name: 'Goblin', side: 'foe', max_hp: 7, hp: 7, temp_hp: 0,
        initiative: 17, conditions: [], concentrating: false, defeated: false,
      },
      s1: {
        id: 's1', name: 'Serah', side: 'ally', max_hp: 30, hp: 30, temp_hp: 0,
        initiative: 12, conditions: [], concentrating: false, defeated: false,
      },
    },
  }
}

function run(state: CombatState, over: Record<string, unknown> = {}) {
  return { run_id: 'run1', status: 'active', can_undo: false, can_redo: false, state, ...over }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
})
afterEach(() => {
  cleanup()
})

async function startedCombat() {
  const view = render(<CombatPage />)
  const ui = within(view.container)
  // Before starting: the encounter picker is shown.
  fireEvent.change(ui.getByRole('combobox'), { target: { value: 'enc1' } })
  fireEvent.click(ui.getByRole('button', { name: /start combat/i }))
  await ui.findByText('Serah') // roster has rendered
  return ui
}

describe('CombatPage', () => {
  it('starts a combat and renders the combatant roster', async () => {
    startCombat.mockResolvedValue(run(stateWith(1, 0)))
    const ui = await startedCombat()

    expect(ui.getByText('Serah')).toBeInTheDocument()
    expect(ui.getAllByText('Goblin').length).toBeGreaterThanOrEqual(1)
    expect(ui.getByRole('heading', { name: /Round 1/i })).toBeInTheDocument()
    expect(startCombat).toHaveBeenCalledWith('camp1', 'enc1')
  })

  it('dispatches next_turn to the server and reconciles the returned state', async () => {
    startCombat.mockResolvedValue(run(stateWith(1, 0)))
    // The server fold advances to round 2 after wrapping the turn order.
    combatAction.mockResolvedValue(run(stateWith(2, 0)))
    const ui = await startedCombat()

    fireEvent.click(ui.getByRole('button', { name: /next turn/i }))

    await waitFor(() =>
      expect(combatAction).toHaveBeenCalledWith('camp1', 'run1', 'next_turn', {}),
    )
    // The reconciled server state (round 2) is rendered.
    expect(await ui.findByRole('heading', { name: /Round 2/i })).toBeInTheDocument()
  })

  it('applies damage optimistically from the keyboard before the server responds', async () => {
    startCombat.mockResolvedValue(run(stateWith(1, 0)))
    // Never resolve, so only the optimistic state is on screen when we assert.
    combatAction.mockReturnValue(new Promise(() => {}))
    const ui = await startedCombat()

    // First combatant (g1, Goblin) is auto-selected; type "5" then Enter = 5 damage.
    fireEvent.keyDown(window, { key: '5' })
    fireEvent.keyDown(window, { key: 'Enter' })

    // Optimistic reducer drops Goblin 7 -> 2 immediately (HP text is unique to the rail card).
    expect(await ui.findByText('2/7')).toBeInTheDocument()
    expect(combatAction).toHaveBeenCalledWith('camp1', 'run1', 'damage', { id: 'g1', amount: 5 })
  })
})
