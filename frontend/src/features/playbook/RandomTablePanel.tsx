import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { rollTable, useRandomTable } from '../../api/hooks'
import type { RollResult } from '../../api/client'

// Shown on a `random_table` entity's page: the rows, and a Roll button that resolves a result
// — including a link when a row points at another entity (an encounter to run, an NPC, or a
// nested table to roll next). This is what turns CoS "random encounters" into a live tool.
export function RandomTablePanel({
  campaignId,
  entityId,
}: {
  campaignId: string
  entityId: string
}) {
  const { data: table } = useRandomTable(campaignId, entityId)
  const [result, setResult] = useState<RollResult | null>(null)
  const [rolling, setRolling] = useState(false)

  if (!table) return null
  const weighted = !table.dice.trim()

  const roll = () => {
    setRolling(true)
    void rollTable(campaignId, entityId)
      .then((r) => setResult(r))
      .finally(() => setRolling(false))
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>
          Random table <span className="badge">{weighted ? 'weighted' : table.dice}</span>
        </h3>
        <button onClick={roll} disabled={rolling || table.rows.length === 0}>
          {rolling ? 'Rolling…' : `Roll ${weighted ? '' : table.dice}`.trim()}
        </button>
      </div>

      {result && (
        <div className="card roll-result" style={{ margin: '10px 0' }}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
            <b>{result.roll != null ? `Rolled ${result.roll}` : 'Result'}</b>
            {result.target_type && result.target_entity_id && (
              <Link to="/entities/$entityId" params={{ entityId: result.target_entity_id }}>
                → {result.target_name} ({result.target_type})
              </Link>
            )}
          </div>
          <p style={{ margin: '4px 0 0' }}>{result.text || <span className="muted">(no text)</span>}</p>
        </div>
      )}

      <ol className="table-rows">
        {table.rows.map((r, i) => (
          <li
            key={i}
            className={'row' + (result?.index === i ? ' rolled' : '')}
            style={{ gap: 8 }}
          >
            <span className="roster-count">
              {weighted ? `×${r.weight ?? 1}` : `${r.min ?? '?'}–${r.max ?? '?'}`}
            </span>
            <span style={{ flex: 1 }}>{r.text}</span>
            {r.target_entity_id && r.target_name && (
              <Link to="/entities/$entityId" params={{ entityId: r.target_entity_id }} className="badge">
                {r.target_name}
              </Link>
            )}
          </li>
        ))}
        {table.rows.length === 0 && <p className="muted">No rows yet — edit this table on the Tables page.</p>}
      </ol>
    </div>
  )
}
