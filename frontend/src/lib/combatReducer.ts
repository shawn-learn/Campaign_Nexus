// TypeScript twin of backend/app/modules/playbook/combat_reducer.py (ADR-005). Powers the
// combat tracker's optimistic UI; kept byte-for-byte identical via shared golden fixtures.
//
// Nothing here rolls a die, and nothing here may — folding the log has to be deterministic
// or undo/redo silently corrupts the combat. Rolls resolve server-side and arrive as literal
// results: set_initiative {value: 17}, never roll_initiative {}. Any change here must land in
// the Python reference and backend/tests/fixtures/combat_golden.json in the same commit.

export interface Combatant {
  id: string
  name: string
  side: string
  /** 'creature' | 'lair'. A lair sits in the initiative order as an ordinary entry. */
  kind: string
  max_hp: number
  hp: number
  temp_hp: number
  initiative: number
  /** Breaks ties before falling back to id (5e: the dex modifier). */
  initiative_tiebreak: number
  conditions: string[]
  concentrating: boolean
  defeated: boolean
  death_saves: { successes: number; failures: number }
  legendary: { max: number; remaining: number }
}

export interface CombatState {
  round: number
  turn_index: number
  order: string[]
  combatants: Record<string, Combatant>
}

export type Action = { type: string } & Record<string, unknown>

// Match Python's int(): coerce to a number, then truncate toward zero. HP/initiative are
// integers, and the reference reducer applies int() to every numeric field — so the twin
// must truncate identically or the two folds diverge on a fractional amount (ADR-005).
const toInt = (x: unknown): number => Math.trunc(Number(x))

export function initialState(): CombatState {
  return { round: 1, turn_index: 0, order: [], combatants: {} }
}

function reorder(state: CombatState): void {
  const ids = Object.keys(state.combatants)
  ids.sort((a, b) => {
    const ca = state.combatants[a]
    const cb = state.combatants[b]
    const d = cb.initiative - ca.initiative
    if (d !== 0) return d
    const t = cb.initiative_tiebreak - ca.initiative_tiebreak
    if (t !== 0) return t
    return a < b ? -1 : a > b ? 1 : 0
  })
  state.order = ids
  state.turn_index = ids.length ? Math.min(state.turn_index, ids.length - 1) : 0
}

// A lair at 0 hp is not a corpse — it has no hit points to lose in the first place.
function isDefeated(m: Combatant): boolean {
  return m.hp === 0 && m.kind !== 'lair'
}

export function applyAction(state: CombatState, action: Action): CombatState {
  const kind = action.type
  const c = state.combatants
  const id = action.id as string

  if (kind === 'add_combatant') {
    const maxHp = toInt(action.max_hp)
    const hp = action.hp === undefined ? maxHp : toInt(action.hp)
    const entryKind = (action.kind as string) ?? 'creature'
    const legendaryMax = toInt(action.legendary_max ?? 0)
    c[id] = {
      id, name: String(action.name), side: (action.side as string) ?? 'foe',
      kind: entryKind,
      max_hp: maxHp, hp, temp_hp: 0, initiative: toInt(action.initiative ?? 0),
      initiative_tiebreak: toInt(action.initiative_tiebreak ?? 0),
      conditions: [], concentrating: false,
      defeated: hp <= 0 && entryKind !== 'lair',
      death_saves: { successes: 0, failures: 0 },
      legendary: { max: legendaryMax, remaining: legendaryMax },
    }
    reorder(state)
  } else if (kind === 'set_initiative') {
    if (c[id]) {
      c[id].initiative = toInt(action.value)
      // Rolling sends the tiebreak along; a manual edit from the rail omits it and leaves
      // whatever the combatant was seeded with.
      if (action.initiative_tiebreak !== undefined) {
        c[id].initiative_tiebreak = toInt(action.initiative_tiebreak)
      }
      reorder(state)
    }
  } else if (kind === 'damage') {
    const m = c[id]
    if (m) {
      const alreadyDown = m.hp === 0 && m.kind !== 'lair'
      let amount = toInt(action.amount)
      const absorbed = Math.min(m.temp_hp, amount)
      m.temp_hp -= absorbed
      amount -= absorbed
      m.hp = Math.max(0, m.hp - amount)
      m.defeated = isDefeated(m)
      if (m.hp === 0) m.concentrating = false
      // Hitting someone who is already down is an automatic failed death save — the single
      // most-forgotten rule at a table, and free to get right here.
      if (alreadyDown && amount > 0) m.death_saves.failures += 1
    }
  } else if (kind === 'heal') {
    const m = c[id]
    if (m) {
      m.hp = Math.min(m.max_hp, m.hp + toInt(action.amount))
      if (m.hp > 0) {
        m.defeated = false
        // Back above 0: nobody is dying any more, so the clock resets.
        m.death_saves = { successes: 0, failures: 0 }
      }
    }
  } else if (kind === 'death_save') {
    const m = c[id]
    if (m) {
      // The *outcome* was decided server-side (a natural 20 is the plugin's rule, not this
      // module's); all that happens here is bookkeeping on a literal result.
      const result = action.result as string
      if (result === 'crit_success') {
        m.hp = Math.min(m.max_hp, 1)
        m.defeated = isDefeated(m)
        m.death_saves = { successes: 0, failures: 0 }
      } else if (result === 'crit_fail') {
        m.death_saves.failures += 2
      } else if (result === 'success') {
        m.death_saves.successes += 1
      } else if (result === 'failure') {
        m.death_saves.failures += 1
      }
    }
  } else if (kind === 'set_temp_hp') {
    if (c[id]) c[id].temp_hp = Math.max(0, toInt(action.amount))
  } else if (kind === 'add_condition') {
    const m = c[id]
    const cond = String(action.condition)
    if (m && !m.conditions.includes(cond)) m.conditions.push(cond)
  } else if (kind === 'remove_condition') {
    const m = c[id]
    const cond = String(action.condition)
    if (m) m.conditions = m.conditions.filter((x) => x !== cond)
  } else if (kind === 'set_concentration') {
    if (c[id]) c[id].concentrating = Boolean(action.on)
  } else if (kind === 'next_turn') {
    if (state.order.length) {
      state.turn_index += 1
      if (state.turn_index >= state.order.length) {
        state.turn_index = 0
        state.round += 1
      }
    }
  } else if (kind === 'remove_combatant') {
    if (c[id]) { delete c[id]; reorder(state) }
  }
  return state
}

export function fold(actions: Action[]): CombatState {
  const state = initialState()
  for (const a of actions) applyAction(state, a)
  return state
}

// Apply one action to a copy (for optimistic UI).
export function applyOptimistic(state: CombatState, action: Action): CombatState {
  const copy: CombatState = JSON.parse(JSON.stringify(state))
  return applyAction(copy, action)
}
