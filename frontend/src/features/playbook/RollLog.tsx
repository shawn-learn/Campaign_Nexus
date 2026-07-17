import { useCombatRolls, type CombatRoll } from '../../api/hooks'
import type { CombatState } from '../../lib/combatReducer'

// Every die thrown this combat, newest first.
//
// The log lives outside the fold on purpose: a roll changes nothing, so folding it would
// give each one an undo slot and make Undo-after-a-roll appear to do nothing. It also
// happens to be the honest model — a die that hit the table can't be un-thrown.

function faces(roll: CombatRoll): string {
  return (roll.detail.dice ?? []).map((d) => (d.kept ? `${d.value}` : `${d.value}✗`)).join(',')
}

export function RollLog({
  campaignId,
  runId,
  state,
}: {
  campaignId: string
  runId: string
  state: CombatState
}) {
  const { data: rolls } = useCombatRolls(campaignId, runId)
  if (!rolls?.length) return null

  return (
    <div className="card">
      <h4 style={{ marginTop: 0 }}>Rolls</h4>
      <ul className="roll-log">
        {rolls.map((r) => {
          const who = r.combatant_id ? state.combatants[r.combatant_id]?.name : null
          return (
            <li key={r.id} title={`${r.expression} (${faces(r)}) = ${r.total}`}>
              <span className="muted">
                {who ? `${who} · ` : ''}{r.label}
              </span>
              <span>
                <b>{r.total}</b>
                {r.target !== null && r.target !== undefined && (
                  <span className="muted"> vs {r.target}</span>
                )}
                {r.outcome && <span className="muted"> · {r.outcome}</span>}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
