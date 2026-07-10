// TypeScript twin of backend/app/modules/playbook/combat_reducer.py (ADR-005). Powers the
// combat tracker's optimistic UI; kept byte-for-byte identical via shared golden fixtures.

export interface Combatant {
  id: string
  name: string
  side: string
  max_hp: number
  hp: number
  temp_hp: number
  initiative: number
  conditions: string[]
  concentrating: boolean
  defeated: boolean
}

export interface CombatState {
  round: number
  turn_index: number
  order: string[]
  combatants: Record<string, Combatant>
}

export type Action = { type: string } & Record<string, unknown>

export function initialState(): CombatState {
  return { round: 1, turn_index: 0, order: [], combatants: {} }
}

function reorder(state: CombatState): void {
  const ids = Object.keys(state.combatants)
  ids.sort((a, b) => {
    const d = state.combatants[b].initiative - state.combatants[a].initiative
    return d !== 0 ? d : a < b ? -1 : a > b ? 1 : 0
  })
  state.order = ids
  state.turn_index = ids.length ? Math.min(state.turn_index, ids.length - 1) : 0
}

export function applyAction(state: CombatState, action: Action): CombatState {
  const kind = action.type
  const c = state.combatants
  const id = action.id as string

  if (kind === 'add_combatant') {
    const maxHp = Number(action.max_hp)
    const hp = action.hp === undefined ? maxHp : Number(action.hp)
    c[id] = {
      id, name: String(action.name), side: (action.side as string) ?? 'foe',
      max_hp: maxHp, hp, temp_hp: 0, initiative: Number(action.initiative ?? 0),
      conditions: [], concentrating: false, defeated: hp <= 0,
    }
    reorder(state)
  } else if (kind === 'set_initiative') {
    if (c[id]) { c[id].initiative = Number(action.value); reorder(state) }
  } else if (kind === 'damage') {
    const m = c[id]
    if (m) {
      let amount = Number(action.amount)
      const absorbed = Math.min(m.temp_hp, amount)
      m.temp_hp -= absorbed
      amount -= absorbed
      m.hp = Math.max(0, m.hp - amount)
      m.defeated = m.hp === 0
      if (m.hp === 0) m.concentrating = false
    }
  } else if (kind === 'heal') {
    const m = c[id]
    if (m) {
      m.hp = Math.min(m.max_hp, m.hp + Number(action.amount))
      if (m.hp > 0) m.defeated = false
    }
  } else if (kind === 'set_temp_hp') {
    if (c[id]) c[id].temp_hp = Math.max(0, Number(action.amount))
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
