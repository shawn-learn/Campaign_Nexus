import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useBeginCombat,
  useCombatRolls,
  useRollInitiative,
  type CombatRoll,
  type CombatRun,
} from '../../api/hooks'
import type { CombatState } from '../../lib/combatReducer'

// "Roll for initiative" — the roster you settle before round 1.
//
// The monsters arrive already rolled (the server rolls them when the combat starts, which is
// what happens at the table the moment you call for it). The players' numbers are yours to
// type: they call them out with the modifier already added, so each PC row is just a number
// box. Tab/Enter walks down them, and Begin lights up once nobody is blank.
//
// A system that doesn't roll for order (Nimble: the party acts, then the monsters do) has no
// dice to offer, so the roll buttons hide and the plugin's ranking stands.

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

/** "1d20+2: (17) +2 = 19" — the faces behind a total, so a suspicious roll is inspectable. */
function rollTitle(roll: CombatRoll | undefined): string | undefined {
  if (!roll) return undefined
  const faces = (roll.detail.dice ?? [])
    .map((d) => (d.kept ? `${d.value}` : `(${d.value} dropped)`))
    .join(', ')
  const mod = roll.detail.modifier ?? 0
  const modText = mod ? ` ${mod > 0 ? '+' : '−'}${Math.abs(mod)}` : ''
  return `${roll.expression}: (${faces})${modText} = ${roll.total}`
}

export function CombatSetup({
  campaignId,
  run,
  onBegun,
  onCancel,
  cancelling,
}: {
  campaignId: string
  run: CombatRun
  onBegun: () => void
  /** Back out before round 1 — the wrong encounter shouldn't have to be fought. */
  onCancel: () => void
  cancelling: boolean
}) {
  const runId = run.run_id
  const state = run.state as unknown as CombatState
  const roll = useRollInitiative(campaignId, runId)
  const begin = useBeginCombat(campaignId, runId)
  const { data: rolls } = useCombatRolls(campaignId, runId)

  // Whether this system rolls for order at all. Nimble's party simply acts first, so
  // offering it a "Roll initiative" button would be a lie — the plugin says so, not a guess
  // from the roster's shape.
  const rollable = !!run.initiative_dice
  // The rows the GM types numbers into: the party's. A system that doesn't roll for order has
  // nothing to wait for, so nobody is asked for a number and Begin is live immediately.
  const pcIds = useMemo(
    () => (rollable ? state.order.filter((id) => state.combatants[id].side === 'ally') : []),
    [state, rollable],
  )

  // Typed totals, keyed by combatant. Seeded blank so a PC's pre-roll modifier (which is not
  // a roll, just a ranking) never masquerades as a real initiative.
  const [typed, setTyped] = useState<Record<string, string>>({})
  const inputs = useRef<Record<string, HTMLInputElement | null>>({})

  // Once a PC has a real value from the server (a typed submit, or Roll all), stop treating
  // their row as blank.
  const submitted = useRef<Set<string>>(new Set())
  useEffect(() => {
    for (const id of pcIds) if (rolledFor(rolls, id)) submitted.current.add(id)
  }, [rolls, pcIds])

  const missing = pcIds.filter(
    (id) => !typed[id]?.trim() && !submitted.current.has(id) && !rolledFor(rolls, id),
  )
  const values = () =>
    Object.fromEntries(
      Object.entries(typed)
        .filter(([, v]) => v.trim() !== '')
        .map(([id, v]) => [id, Number(v)]),
    )

  const rollFoes = () => roll.mutate({ scope: 'foes', values: values() })
  const rollAll = () => roll.mutate({ scope: 'all', values: values() })
  const rollOne = (id: string) => roll.mutate({ scope: 'ids', ids: [id], values: values() })

  const start = () => {
    // Submit whatever is typed, then begin — one press, not two.
    const typedValues = values()
    if (Object.keys(typedValues).length) {
      roll.mutate(
        { scope: 'ids', ids: [], values: typedValues },
        { onSuccess: () => begin.mutate(undefined, { onSuccess: onBegun }) },
      )
    } else {
      begin.mutate(undefined, { onSuccess: onBegun })
    }
  }

  // Enter walks to the next empty PC box, so five players is five numbers and five Enters.
  const onKey = (e: React.KeyboardEvent<HTMLInputElement>, id: string) => {
    if (e.key !== 'Enter') return
    e.preventDefault()
    const i = pcIds.indexOf(id)
    const next = pcIds.slice(i + 1).find((n) => !typed[n]?.trim())
    if (next) inputs.current[next]?.focus()
    else if (!missing.length) start()
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Roll for initiative</h2>
        <div className="row" style={{ gap: 6 }}>
          <button className="ghost" disabled={cancelling} onClick={onCancel}>
            {cancelling ? 'Cancelling…' : 'Cancel combat'}
          </button>
          {rollable && (
            <>
              <button className="ghost" disabled={roll.isPending} onClick={rollFoes}>
                Roll monsters
              </button>
              <button className="ghost" disabled={roll.isPending} onClick={rollAll}>
                Roll all
              </button>
            </>
          )}
          <button disabled={begin.isPending || missing.length > 0} onClick={start}>
            {begin.isPending ? 'Starting…' : 'Begin'}
          </button>
        </div>
      </div>
      <p className="muted combat-hint">
        {rollable
          ? 'Monsters are rolled. Type what your players call out — modifier included — then Begin.'
          : 'This system rolls no initiative; the order below is its own. Begin when ready.'}
      </p>
      {missing.length > 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          Waiting on {missing.length} player {missing.length === 1 ? 'number' : 'numbers'}.
        </p>
      )}
      {roll.isError && (
        <p className="muted" style={{ color: 'var(--danger)' }}>
          Couldn't roll: {errorText(roll.error)}
        </p>
      )}

      <ul className="initiative-rail setup-rail">
        {state.order.map((id) => {
          const c = state.combatants[id]
          const theirRoll = rolledFor(rolls, id)
          // A box to type into only where a number is actually owed: a PC, in a system that
          // rolls, who hasn't been rolled for. Everyone else just shows their number.
          const awaitingPlayer = rollable && c.side === 'ally' && !theirRoll
          return (
            <li key={id} className={`combatant-card side-${c.side}`}>
              <div className="cc-top">
                {awaitingPlayer ? (
                  <input
                    ref={(el) => { inputs.current[id] = el }}
                    className="cc-init-input"
                    type="number"
                    inputMode="numeric"
                    aria-label={`${c.name} initiative`}
                    placeholder="—"
                    value={typed[id] ?? ''}
                    onChange={(e) => setTyped((t) => ({ ...t, [id]: e.target.value }))}
                    onKeyDown={(e) => onKey(e, id)}
                  />
                ) : (
                  <span className="cc-init" title={rollTitle(theirRoll)}>{c.initiative}</span>
                )}
                <span className="cc-name">{c.name}</span>
                {rollable && (
                  <button
                    className="linkish cc-reroll"
                    disabled={roll.isPending}
                    title={`Re-roll ${c.name}`}
                    aria-label={`Re-roll ${c.name}`}
                    onClick={() => rollOne(id)}
                  >
                    ↻
                  </button>
                )}
              </div>
              <div className="cc-setup-meta muted">
                {c.max_hp > 0 && <span>{c.hp}/{c.max_hp} hp</span>}
                {theirRoll && <span>rolled {theirRoll.expression}</span>}
                {awaitingPlayer && <span>waiting for their roll</span>}
              </div>
            </li>
          )
        })}
      </ul>
    </>
  )
}

function rolledFor(rolls: CombatRoll[] | undefined, id: string): CombatRoll | undefined {
  // Newest first from the server, so the first match is the roll that stands.
  return rolls?.find((r) => r.combatant_id === id && r.kind === 'initiative')
}
