import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, cleanup, within, fireEvent, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CombatState, Combatant } from '../../lib/combatReducer'

// The reducer twin is unit-tested elsewhere (combatReducer.test.ts); this covers the wiring
// on top: the optimistic-then-reconcile action flow, rollback when the server rejects, and
// that combat state renders.
//
// The mock sits at the *client* layer, not the hooks layer, and the page runs inside a real
// QueryClientProvider — because the optimistic apply and its rollback live inside the combat
// hooks now. Mocking the hooks (as this file used to) would stub out the very thing under
// test and pass no matter how broken the rollback was.
//
// Note the first combatant is auto-selected, so its name appears twice (initiative rail +
// detail panel) — assertions target unambiguous text ("Serah" is roster-only; HP text and
// the round heading are unique).
vi.mock('../../shell/useActiveCampaign', () => ({
  useActiveCampaign: () => ({
    campaign: { id: 'camp1', rule_system_id: 'dnd5e' },
    isLoading: false,
  }),
}))

const GET = vi.fn()
const POST = vi.fn()
vi.mock('../../api/client', () => ({
  api: {
    GET: (...args: unknown[]) => GET(...args),
    POST: (...args: unknown[]) => POST(...args),
    PATCH: vi.fn(),
    DELETE: vi.fn(),
  },
}))

import { CombatPage } from './CombatPage'

// One place to absorb combatant-shape changes, so adding a reducer field doesn't mean
// editing every fixture in the file.
function combatant(over: Partial<Combatant> & Pick<Combatant, 'id'>): Combatant {
  return {
    name: 'Someone', side: 'foe', kind: 'creature', max_hp: 10, hp: 10, temp_hp: 0,
    initiative: 0, initiative_tiebreak: 0, conditions: [], concentrating: false,
    defeated: false, death_saves: { successes: 0, failures: 0 },
    legendary: { max: 0, remaining: 0 },
    ...over,
  }
}

function stateWith(round: number, turnIndex: number): CombatState {
  return {
    round,
    turn_index: turnIndex,
    order: ['g1', 's1'],
    combatants: {
      g1: combatant({ id: 'g1', name: 'Goblin', side: 'foe', max_hp: 7, hp: 7, initiative: 17 }),
      s1: combatant({ id: 's1', name: 'Serah', side: 'ally', max_hp: 30, hp: 30, initiative: 12 }),
    },
  }
}

const DEATH_RULES = { supported: true, dice: '1d20', dc: 10, successes: 3, failures: 3 }

function run(state: CombatState, over: Record<string, unknown> = {}) {
  return {
    run_id: 'run1', status: 'active', can_undo: false, can_redo: false, state,
    initiative_dice: '1d20', death_saves: DEATH_RULES, ...over,
  }
}

/** openapi-fetch's shape: `{ data }` on success, `{ error }` on failure. */
const ok = (data: unknown) => Promise.resolve({ data })
const fail = (detail: string) => Promise.resolve({ error: { detail } })

// What GET /combats/{run_id} serves. Starting a combat seeds the query cache, but the query
// is stale immediately and refetches — so the fetch has to agree with the seed, or it
// overwrites the run the mutation just returned.
let served: unknown = null
/** What GET /rolls serves — the run's initiative rolls. */
let rolls: unknown[] = []
/** What GET /combatants/{id}/attacks serves. */
let attacks: unknown[] = []

const SCIMITAR = {
  index: 0, name: 'Scimitar', kind: 'melee', to_hit: 4,
  reach: '5 ft.', target: 'one target',
  damage: [{ dice: '1d6+2', type: 'slashing' }], save: null, description: null,
}

/** A to-hit roll of 17 against AC 15. */
const HIT_RESULT = {
  action_name: 'Scimitar', attacker_id: 'g1', target_id: 's1', target_ac: 15,
  outcome: 'hit', total_damage: 5,
  to_hit: {
    id: 'r-hit', combatant_id: 'g1', kind: 'attack', label: 'Scimitar',
    expression: '1d20+4', mode: 'normal', total: 17, target: 15, outcome: 'hit',
    recorded_at_real: 'now',
    detail: { dice: [{ sides: 20, value: 13, kept: true, sign: 1 }], modifier: 4 },
  },
  damage: [{
    id: 'r-dmg', combatant_id: 's1', kind: 'damage', label: 'Scimitar (slashing)',
    expression: '1d6+2', mode: 'normal', total: 5, target: null, outcome: null,
    recorded_at_real: 'now',
    detail: { dice: [{ sides: 6, value: 3, kept: true, sign: 1 }], modifier: 2 },
  }],
  save: null, description: null,
}

// Built fresh per test, but referenced (not constructed) by the wrapper — constructing it
// inside the wrapper body would hand React a new cache on every render.
let qc: QueryClient

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>
}

beforeEach(() => {
  // resetAllMocks, not clearAllMocks: clear leaves the mockReturnValueOnce queue intact, so
  // a test that queues a never-resolving promise and never consumes it hands that promise to
  // the *next* test's start call — which then hangs with no roster and a baffling error.
  vi.resetAllMocks()
  localStorage.clear()
  qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  served = null
  rolls = []
  attacks = []
  GET.mockImplementation((path: string) => {
    if (path.includes('/encounters')) return ok([{ id: 'enc1', name: 'Goblin Ambush' }])
    if (path.includes('/conditions')) {
      return ok([{ id: 'prone', name: 'Prone', description: 'Disadvantage on attacks.' }])
    }
    if (path.includes('/rolls')) return ok(rolls)
    if (path.includes('/attacks')) return ok(attacks)
    if (path.includes('/monsters')) return ok([{ id: 'm-ogre', name: 'Ogre' }])
    if (path.includes('/combats/')) return served ? ok(served) : fail('combat not found')
    return ok(null)
  })
})
afterEach(cleanup)

/** Start a combat that stays on the initiative roster (the server opens runs in `setup`). */
async function startedSetup(initial = run(stateWith(1, 0), { status: 'setup' })) {
  served = initial
  POST.mockReturnValueOnce(ok(initial))
  const view = render(<CombatPage />, { wrapper })
  const ui = within(view.container)
  await ui.findByRole('option', { name: 'Goblin Ambush' })
  fireEvent.change(ui.getByRole('combobox'), { target: { value: 'enc1' } })
  fireEvent.click(ui.getByRole('button', { name: /start combat/i }))
  await ui.findByRole('heading', { name: /roll for initiative/i })
  return ui
}

async function startedCombat(initial = run(stateWith(1, 0))) {
  served = initial
  POST.mockReturnValueOnce(ok(initial)) // the start call
  const view = render(<CombatPage />, { wrapper })
  const ui = within(view.container)
  // Wait for the *option*, not the select: the select renders immediately but is empty
  // until the encounters query settles, and selecting a value that has no option yet
  // silently leaves the select on ''.
  await ui.findByRole('option', { name: 'Goblin Ambush' })
  fireEvent.change(ui.getByRole('combobox'), { target: { value: 'enc1' } })
  fireEvent.click(ui.getByRole('button', { name: /start combat/i }))
  await ui.findByText('Serah') // roster has rendered
  return ui
}

describe('CombatPage', () => {
  it('starts a combat and renders the combatant roster', async () => {
    const ui = await startedCombat()

    expect(ui.getByText('Serah')).toBeInTheDocument()
    expect(ui.getAllByText('Goblin').length).toBeGreaterThanOrEqual(1)
    expect(ui.getByRole('heading', { name: /Round 1/i })).toBeInTheDocument()
  })

  it('dispatches next_turn to the server and reconciles the returned state', async () => {
    const ui = await startedCombat()
    // The server fold wraps the turn order round to round 2.
    served = run(stateWith(2, 0))
    POST.mockReturnValueOnce(ok(served))

    fireEvent.click(ui.getByRole('button', { name: /next turn/i }))

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
        expect.objectContaining({ body: { action_type: 'next_turn', payload: {} } }),
      ),
    )
    expect(await ui.findByRole('heading', { name: /Round 2/i })).toBeInTheDocument()
  })

  it('applies damage optimistically from the keyboard before the server responds', async () => {
    const ui = await startedCombat()
    POST.mockReturnValueOnce(new Promise(() => {})) // never resolves: only optimistic is shown

    // First combatant (g1, Goblin) is auto-selected; type "5" then Enter = 5 damage.
    fireEvent.keyDown(window, { key: '5' })
    fireEvent.keyDown(window, { key: 'Enter' })

    // The optimistic reducer drops Goblin 7 -> 2 immediately.
    expect(await ui.findByText('2/7')).toBeInTheDocument()
  })

  it('rolls the optimistic damage back when the server rejects it', async () => {
    const ui = await startedCombat()
    POST.mockReturnValueOnce(fail('combat already ended')) // the action is refused

    fireEvent.keyDown(window, { key: '5' })
    fireEvent.keyDown(window, { key: 'Enter' })

    // It must not stay at 2/7. Before the rollback existed the optimistic state sat there
    // forever, showing the GM a wound the server never recorded.
    await waitFor(() => expect(ui.getByText('7/7')).toBeInTheDocument())
    expect(ui.queryByText('2/7')).not.toBeInTheDocument()
    expect(ui.getByText(/combat already ended/i)).toBeInTheDocument()
  })

  it('shows the initiative roster while the run is in setup', async () => {
    // Goblin is a rolled monster; Serah is a PC waiting for the number her player calls out.
    rolls = [{
      id: 'r1', combatant_id: 'g1', kind: 'initiative', label: 'Initiative',
      expression: '1d20+2', mode: 'normal', total: 17, target: null, outcome: null,
      recorded_at_real: 'now',
      detail: { dice: [{ sides: 20, value: 15, kept: true, sign: 1 }], modifier: 2 },
    }]
    const ui = await startedSetup()

    expect(ui.getByRole('heading', { name: /roll for initiative/i })).toBeInTheDocument()
    // The monster's roll is shown, with its faces inspectable.
    expect(ui.getByTitle('1d20+2: (15) +2 = 17')).toBeInTheDocument()
    // The PC gets a box to type into; the monster does not.
    expect(ui.getByLabelText('Serah initiative')).toBeInTheDocument()
    expect(ui.queryByLabelText('Goblin initiative')).not.toBeInTheDocument()
  })

  it('holds Begin until every player has a number, then submits them with it', async () => {
    const ui = await startedSetup()
    const begin = ui.getByRole('button', { name: /begin/i })
    expect(begin).toBeDisabled() // Serah's number is missing

    fireEvent.change(ui.getByLabelText('Serah initiative'), { target: { value: '18' } })
    expect(begin).toBeEnabled()

    served = run(stateWith(1, 0), { status: 'active' })
    POST.mockReturnValueOnce(ok(run(stateWith(1, 0), { status: 'setup' }))) // values submitted
      .mockReturnValueOnce(ok(served)) // begin
    fireEvent.click(begin)

    // The typed total goes up verbatim — the player already added their modifier.
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/initiative',
        expect.objectContaining({ body: expect.objectContaining({ values: { s1: 18 } }) }),
      ),
    )
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/begin',
        expect.anything(),
      ),
    )
  })

  it('rolls just the monsters when asked', async () => {
    const ui = await startedSetup()
    POST.mockReturnValueOnce(ok(run(stateWith(1, 0), { status: 'setup' })))

    fireEvent.click(ui.getByRole('button', { name: /roll monsters/i }))

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/initiative',
        expect.objectContaining({ body: expect.objectContaining({ scope: 'foes' }) }),
      ),
    )
  })

  it('offers no roll in a system that does not roll for order', async () => {
    // Nimble: the party acts, then the monsters do. Offering a d20 would be a lie, and
    // nobody is waiting on a number — so Begin is live at once.
    const ui = await startedSetup(
      run(stateWith(1, 0), { status: 'setup', initiative_dice: null }),
    )

    expect(ui.queryByRole('button', { name: /roll monsters/i })).not.toBeInTheDocument()
    expect(ui.queryByRole('button', { name: /roll all/i })).not.toBeInTheDocument()
    expect(ui.queryByLabelText('Serah initiative')).not.toBeInTheDocument()
    expect(ui.getByRole('button', { name: /begin/i })).toBeEnabled()
  })

  it('rolls an attack against a default target and reports the verdict', async () => {
    attacks = [SCIMITAR]
    const ui = await startedCombat()
    // Goblin (foe) is auto-selected; the target defaults to the first standing ally.
    await ui.findByRole('button', { name: /scimitar/i })

    POST.mockReturnValueOnce(ok(HIT_RESULT))
    fireEvent.click(ui.getByRole('button', { name: /scimitar/i }))

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/attack',
        expect.objectContaining({
          body: { attacker_id: 'g1', action_index: 0, target_id: 's1', mode: 'normal' },
        }),
      ),
    )
    expect(await ui.findByText('HIT')).toBeInTheDocument()
    expect(ui.getByText('vs AC 15')).toBeInTheDocument()
    // The faces behind the total, so a surprising roll is inspectable rather than magic.
    // (Not asserting on "17" alone — the goblin's initiative is also 17.)
    expect(ui.getByText(/1d20\+4 \(13\) \+4/)).toBeInTheDocument()
    expect(ui.getByText(/1d6\+2 \(3\) \+2 = 5/)).toBeInTheDocument()
  })

  it('applies nothing until asked, then fires a damage action carrying the roll id', async () => {
    attacks = [SCIMITAR]
    const ui = await startedCombat()
    await ui.findByRole('button', { name: /scimitar/i })
    POST.mockReturnValueOnce(ok(HIT_RESULT))
    fireEvent.click(ui.getByRole('button', { name: /scimitar/i }))
    await ui.findByText('HIT')

    // The roll landed but Serah is untouched — the ruling is the GM's to make.
    expect(ui.getByText('30/30')).toBeInTheDocument()
    expect(POST).not.toHaveBeenCalledWith(
      '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
      expect.anything(),
    )

    POST.mockReturnValueOnce(new Promise(() => {}))
    fireEvent.click(ui.getByRole('button', { name: /apply 5/i }))

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
        expect.objectContaining({
          body: {
            action_type: 'damage',
            // roll_id makes "where did this 5 come from" answerable from the log.
            payload: { id: 's1', amount: 5, roll_id: 'r-dmg' },
          },
        }),
      ),
    )
    expect(await ui.findByText('25/30')).toBeInTheDocument() // optimistic
  })

  it('rolls with advantage when asked', async () => {
    attacks = [SCIMITAR]
    const ui = await startedCombat()
    await ui.findByRole('button', { name: /scimitar/i })

    fireEvent.change(ui.getByLabelText(/roll mode/i), { target: { value: 'advantage' } })
    POST.mockReturnValueOnce(ok(HIT_RESULT))
    fireEvent.click(ui.getByRole('button', { name: /scimitar/i }))

    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/attack',
        expect.objectContaining({ body: expect.objectContaining({ mode: 'advantage' }) }),
      ),
    )
  })

  it('shows no attack panel for a combatant with nothing to swing', async () => {
    attacks = []
    const ui = await startedCombat()
    expect(ui.queryByRole('heading', { name: /^attacks$/i })).not.toBeInTheDocument()
  })

  it('shows no death-save row while everyone is standing', async () => {
    const ui = await startedCombat()
    expect(ui.queryByText(/dying/i)).not.toBeInTheDocument()
  })

  it('tracks death saves for a downed creature', async () => {
    const down = stateWith(1, 0)
    down.combatants.g1.hp = 0
    down.combatants.g1.death_saves = { successes: 1, failures: 2 }
    const ui = await startedCombat(run(down))

    expect(ui.getByText(/dying/i)).toBeInTheDocument()
    expect(ui.getByLabelText('1 of 3')).toBeInTheDocument() // successes
    expect(ui.getByLabelText('2 of 3')).toBeInTheDocument() // failures
    expect(ui.getByRole('button', { name: /roll 1d20 vs DC 10/i })).toBeInTheDocument()
  })

  it('stops offering the roll once the saves have settled it', async () => {
    const down = stateWith(1, 0)
    down.combatants.g1.hp = 0
    down.combatants.g1.death_saves = { successes: 0, failures: 3 }
    const ui = await startedCombat(run(down))

    expect(ui.getByText('Dead')).toBeInTheDocument()
    expect(ui.queryByRole('button', { name: /roll 1d20/i })).not.toBeInTheDocument()
  })

  it('shows no death-save row in a system that has none', async () => {
    // Nimble has no death saves; inventing a d20 for it would be a lie.
    const down = stateWith(1, 0)
    down.combatants.g1.hp = 0
    const ui = await startedCombat(run(down, { death_saves: { supported: false } }))
    expect(ui.queryByText(/dying/i)).not.toBeInTheDocument()
  })

  it('asks about concentration when damage lands on a caster', async () => {
    const s = stateWith(1, 0)
    s.combatants.s1.concentrating = true
    const ui = await startedCombat(run(s))

    // 9 damage to Serah (30 hp): still up, so the question is live. DC = max(10, 4) = 10.
    fireEvent.keyDown(window, { key: 'ArrowDown' }) // select Serah
    POST.mockReturnValueOnce(new Promise(() => {}))
    fireEvent.keyDown(window, { key: '9' })
    fireEvent.keyDown(window, { key: 'Enter' })

    expect(await ui.findByText(/Serah is concentrating/i)).toBeInTheDocument()
    expect(ui.getByText(/DC 10/)).toBeInTheDocument()
  })

  it('uses half the damage as the DC when that is higher', async () => {
    const s = stateWith(1, 0)
    s.combatants.s1.concentrating = true
    const ui = await startedCombat(run(s))

    fireEvent.keyDown(window, { key: 'ArrowDown' })
    POST.mockReturnValueOnce(new Promise(() => {}))
    fireEvent.keyDown(window, { key: '2' })
    fireEvent.keyDown(window, { key: '6' }) // 26 damage -> DC 13
    fireEvent.keyDown(window, { key: 'Enter' })

    expect(await ui.findByText(/DC 13/)).toBeInTheDocument()
  })

  it('breaks concentration only when told to', async () => {
    const s = stateWith(1, 0)
    s.combatants.s1.concentrating = true
    const ui = await startedCombat(run(s))
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    POST.mockReturnValueOnce(ok(run(s)))
    fireEvent.keyDown(window, { key: '9' })
    fireEvent.keyDown(window, { key: 'Enter' })
    await ui.findByText(/Serah is concentrating/i)

    // Held: the prompt goes away and nothing is dispatched.
    fireEvent.click(ui.getByRole('button', { name: /^held$/i }))
    expect(ui.queryByText(/is concentrating/i)).not.toBeInTheDocument()
    expect(POST).not.toHaveBeenCalledWith(
      '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
      expect.objectContaining({
        body: expect.objectContaining({ action_type: 'set_concentration' }),
      }),
    )
  })

  it('does not ask about concentration when the hit drops them', async () => {
    // Falling to 0 breaks concentration outright — the reducer does it, so asking would
    // be theatre.
    const s = stateWith(1, 0)
    s.combatants.s1.concentrating = true
    const ui = await startedCombat(run(s))
    fireEvent.keyDown(window, { key: 'ArrowDown' })
    POST.mockReturnValueOnce(new Promise(() => {}))
    fireEvent.keyDown(window, { key: '4' })
    fireEvent.keyDown(window, { key: '0' }) // 40 vs 30 hp
    fireEvent.keyDown(window, { key: 'Enter' })

    await waitFor(() => expect(ui.getByText('0/30')).toBeInTheDocument())
    expect(ui.queryByText(/is concentrating/i)).not.toBeInTheDocument()
  })

  it('sets temp HP from the keyboard', async () => {
    // set_temp_hp rendered as "(+N)" from day one but nothing could ever set it.
    const ui = await startedCombat()
    POST.mockReturnValueOnce(new Promise(() => {})) // optimistic only

    fireEvent.keyDown(window, { key: '5' })
    fireEvent.keyDown(window, { key: 't' })

    expect(await ui.findByText('7/7 (+5)')).toBeInTheDocument()
  })

  it('marks a combatant bloodied at half HP', async () => {
    const wounded = stateWith(1, 0)
    wounded.combatants.g1.hp = 3 // 3 of 7 — at or below half
    const ui = await startedCombat(run(wounded))

    expect(ui.getByTitle('bloodied')).toBeInTheDocument()
  })

  it('confirms before removing a combatant', async () => {
    const ui = await startedCombat()
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    POST.mockReturnValueOnce(ok(run(stateWith(1, 0))))

    fireEvent.click(ui.getByRole('button', { name: /^remove$/i }))

    // Declining must not fire the action — this is the one destructive control here.
    expect(confirmSpy).toHaveBeenCalled()
    expect(POST).not.toHaveBeenCalledWith(
      '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
      expect.objectContaining({ body: expect.objectContaining({ action_type: 'remove_combatant' }) }),
    )

    confirmSpy.mockReturnValue(true)
    fireEvent.click(ui.getByRole('button', { name: /^remove$/i }))
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions',
        expect.objectContaining({
          body: { action_type: 'remove_combatant', payload: { id: 'g1' } },
        }),
      ),
    )
    confirmSpy.mockRestore()
  })

  it('adds a monster from the bestiary by id, letting the server seed it', async () => {
    const ui = await startedCombat()
    fireEvent.keyDown(window, { key: 'a' })

    const dialog = within(await ui.findByRole('dialog'))
    // Wait for the option, not the select — the same trap as the encounter picker: setting a
    // value that has no option yet silently leaves the select empty.
    await dialog.findByRole('option', { name: 'Ogre' })
    fireEvent.change(dialog.getByLabelText(/monster/i), { target: { value: 'm-ogre' } })
    POST.mockReturnValueOnce(ok(run(stateWith(1, 0))))
    fireEvent.click(dialog.getByRole('button', { name: /^add$/i }))

    // Only the id goes up: HP and the initiative die come from the plugin, server-side.
    await waitFor(() =>
      expect(POST).toHaveBeenCalledWith(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/combatants',
        expect.objectContaining({
          body: expect.objectContaining({ monster_id: 'm-ogre', count: 1, side: 'foe' }),
        }),
      ),
    )
  })

  it("offers the rule system's conditions rather than a hard-coded list", async () => {
    const ui = await startedCombat()

    // 'Prone' comes from the mocked /conditions response, with its description as a tooltip.
    const prone = await ui.findByRole('button', { name: 'Prone' })
    expect(prone).toHaveAttribute('title', 'Disadvantage on attacks.')
    // 'stunned' was in the old hard-coded six but is not in this system's list, so it is gone.
    expect(ui.queryByRole('button', { name: /stunned/i })).not.toBeInTheDocument()
  })
})
