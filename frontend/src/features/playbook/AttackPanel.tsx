import { useEffect, useMemo, useState } from 'react'
import {
  useCombatantAttacks,
  useRollAttack,
  type AttackResult,
  type CombatActionType,
  type CombatRoll,
} from '../../api/hooks'
import type { CombatState } from '../../lib/combatReducer'

// Click an attack, see what the dice said, then decide.
//
// The roll never applies itself. Resistance, cover, "he ducks behind the pillar" — none of
// that is knowable server-side, and spending the GM's judgement call to save one click is a
// bad trade. So: roll, report, and leave an Apply button for when the ruling is made.

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

/** "(17) +4" — the faces behind a total, so a surprising roll is inspectable. */
function faces(roll: CombatRoll): string {
  const dice = (roll.detail.dice ?? [])
    .map((d) => (d.kept ? `${d.value}` : `${d.value}✗`))
    .join(', ')
  const mod = roll.detail.modifier ?? 0
  return mod ? `(${dice}) ${mod > 0 ? '+' : '−'}${Math.abs(mod)}` : `(${dice})`
}

const VERDICT: Record<string, string> = {
  hit: 'HIT', miss: 'MISS', crit: 'CRITICAL HIT', fumble: 'FUMBLE',
}

export function AttackPanel({
  campaignId,
  runId,
  attackerId,
  state,
  onApply,
}: {
  campaignId: string
  runId: string
  attackerId: string
  state: CombatState
  onApply: (type: CombatActionType, payload: Record<string, unknown>) => void
}) {
  const { data: attacks } = useCombatantAttacks(campaignId, runId, attackerId)
  const roll = useRollAttack(campaignId, runId)
  const [result, setResult] = useState<AttackResult | null>(null)
  const [mode, setMode] = useState<'normal' | 'advantage' | 'disadvantage'>('normal')

  const attacker = state.combatants[attackerId]

  // Default the target to the first standing combatant on the other side — usually right,
  // and always overridable. Saves a click on the overwhelmingly common case.
  const candidates = useMemo(
    () =>
      state.order
        .map((id) => state.combatants[id])
        .filter((c) => c.id !== attackerId && !c.defeated && c.kind !== 'lair'),
    [state, attackerId],
  )
  const [targetId, setTargetId] = useState('')
  useEffect(() => {
    const foe = candidates.find((c) => c.side !== attacker?.side)
    setTargetId(foe?.id ?? '')
    setResult(null)
  }, [attackerId, attacker?.side, candidates])

  if (!attacks?.length) return null

  const fire = (index: number) => {
    roll.mutate(
      { attacker_id: attackerId, action_index: index, target_id: targetId || null, mode },
      { onSuccess: setResult },
    )
  }

  const damage = result?.damage ?? []

  const apply = () => {
    if (!result?.target_id || !result.total_damage) return
    onApply('damage', {
      id: result.target_id,
      amount: result.total_damage,
      // Provenance: the reducer ignores this, but "where did this 8 come from" stays
      // answerable from the log.
      roll_id: damage[0]?.id,
    })
    setResult(null)
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h4 style={{ margin: 0 }}>Attacks</h4>
        <select
          aria-label="Roll mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        >
          <option value="normal">Normal</option>
          <option value="advantage">Advantage</option>
          <option value="disadvantage">Disadvantage</option>
        </select>
      </div>

      <label className="field">
        <span>Target</span>
        <select value={targetId} onChange={(e) => setTargetId(e.target.value)}>
          <option value="">— no target (just roll) —</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
      </label>

      <div className="attack-list">
        {attacks.map((a) => (
          <button
            key={a.index}
            className="ghost attack-btn"
            disabled={roll.isPending}
            onClick={() => fire(a.index)}
          >
            <b>{a.name}</b>
            <span className="attack-meta">
              {a.to_hit !== null && a.to_hit !== undefined
                ? ` ${a.to_hit >= 0 ? '+' : ''}${a.to_hit} to hit`
                : ''}
              {(a.damage ?? []).length
                ? ` · ${(a.damage ?? []).map((d) => `${d.dice} ${d.type}`.trim()).join(' + ')}`
                : ''}
            </span>
          </button>
        ))}
      </div>

      {roll.isError && (
        <p className="muted" style={{ color: 'var(--danger)' }}>
          Couldn't roll: {errorText(roll.error)}
        </p>
      )}

      {result && (
        <div className={`roll-card ${result.outcome ?? ''}`}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
            <b>{result.action_name}</b>
            <span className="roll-outcome">{VERDICT[result.outcome ?? ''] ?? ''}</span>
          </div>

          {result.to_hit && (
            <div>
              <span className="roll-total">{result.to_hit.total}</span>{' '}
              {result.target_ac !== null && result.target_ac !== undefined ? (
                <span className="muted">vs AC {result.target_ac}</span>
              ) : (
                <span className="muted">— no AC on record; your call</span>
              )}
              <div className="roll-faces">{result.to_hit.expression} {faces(result.to_hit)}</div>
            </div>
          )}

          {damage.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <b>{result.total_damage}</b> damage
              {damage.map((d) => (
                <div key={d.id} className="roll-faces">
                  {d.label}: {d.expression} {faces(d)} = {d.total}
                </div>
              ))}
            </div>
          )}

          {result.save && (
            <p className="muted" style={{ fontSize: 11, marginBottom: 0 }}>
              {result.save.ability.toUpperCase()} save DC {result.save.dc}
              {result.save.half_on_success ? ' (half on a success)' : ''}
            </p>
          )}
          {result.description && (
            <p className="muted" style={{ fontSize: 11, marginBottom: 0 }}>{result.description}</p>
          )}

          <div className="row" style={{ gap: 6, marginTop: 8 }}>
            <button
              disabled={!result.target_id || !result.total_damage}
              onClick={apply}
              title={
                result.target_id
                  ? 'Apply this damage to the target'
                  : 'Pick a target to apply damage'
              }
            >
              Apply {result.total_damage || ''}
            </button>
            <button className="ghost" onClick={() => setResult(null)}>Dismiss</button>
          </div>
        </div>
      )}
    </div>
  )
}
