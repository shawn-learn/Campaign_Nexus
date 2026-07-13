import { useCallback, useEffect, useState } from 'react'
import {
  combatAction,
  combatRedo,
  combatUndo,
  endCombat,
  getCombat,
  startCombat,
  useEncounters,
} from '../../api/hooks'
import { applyOptimistic } from '../../lib/combatReducer'
import type { CombatState } from '../../lib/combatReducer'
import { useStatBlock } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { StatBlockView } from '../rules/StatBlockView'

const CONDITIONS = ['prone', 'poisoned', 'stunned', 'restrained', 'frightened', 'grappled']

interface RunOut {
  run_id: string
  status: string
  can_undo: boolean
  can_redo: boolean
  state: CombatState
  combatant_blocks?: Record<string, string>
}

// Combat tracker (FR-12.3, ADR-005). Keyboard-first: ↑/↓ select, digits build a number,
// Enter = damage, h = heal, Space = next turn, u/r = undo/redo. Optimistic via the TS
// reducer twin so each action feels instant (NFR-1.3), reconciled with the server fold.
export function CombatPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const systemId = campaign?.rule_system_id ?? null
  const { data: encounters } = useEncounters(campaignId)

  const [pick, setPick] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [state, setState] = useState<CombatState | null>(null)
  const [meta, setMeta] = useState({ can_undo: false, can_redo: false, status: 'active' })
  const [blocks, setBlocks] = useState<Record<string, string>>({})
  const [selected, setSelected] = useState<string | null>(null)
  const [buffer, setBuffer] = useState('')
  const [summary, setSummary] = useState<string | null>(null)

  const storageKey = campaignId ? `nexus.combat.${campaignId}` : null

  const ingest = useCallback((run: RunOut) => {
    setRunId(run.run_id)
    setState(run.state)
    setMeta({ can_undo: run.can_undo, can_redo: run.can_redo, status: run.status })
    setBlocks(run.combatant_blocks ?? {})
    if (storageKey) localStorage.setItem(storageKey, run.run_id)
  }, [storageKey])

  // Resume an in-progress combat after a page refresh (state folds on the server).
  useEffect(() => {
    if (!campaignId || !storageKey || runId) return
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      void getCombat(campaignId, saved)
        .then((r) => ingest(r as RunOut))
        .catch(() => localStorage.removeItem(storageKey))
    }
  }, [campaignId, storageKey, runId, ingest])

  const begin = async () => {
    if (!campaignId || !pick) return
    ingest((await startCombat(campaignId, pick)) as RunOut)
    setSummary(null)
  }

  const newCombat = () => {
    if (storageKey) localStorage.removeItem(storageKey)
    setRunId(null)
    setState(null)
    setSelected(null)
    setSummary(null)
  }

  const push = useCallback(
    async (type: string, payload: Record<string, unknown>) => {
      if (!campaignId || !runId || !state) return
      setState(applyOptimistic(state, { type, ...payload })) // instant
      ingest((await combatAction(campaignId, runId, type, payload)) as RunOut) // reconcile
    },
    [campaignId, runId, state, ingest],
  )

  const doUndo = useCallback(async () => {
    if (campaignId && runId) ingest((await combatUndo(campaignId, runId)) as RunOut)
  }, [campaignId, runId, ingest])
  const doRedo = useCallback(async () => {
    if (campaignId && runId) ingest((await combatRedo(campaignId, runId)) as RunOut)
  }, [campaignId, runId, ingest])

  const finish = async () => {
    if (!campaignId || !runId) return
    const s = (await endCombat(campaignId, runId)) as {
      rounds: number; defeated: string[]; duration_seconds: number
    }
    setSummary(`Combat ended after ${s.rounds} round(s); ${s.defeated.length} foe(s) defeated.`)
    setMeta((m) => ({ ...m, status: 'completed' }))
  }

  // Keyboard controls.
  useEffect(() => {
    if (!state || meta.status !== 'active') return
    const order = state.order
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
      if (e.key >= '0' && e.key <= '9') { setBuffer((b) => (b + e.key).slice(0, 4)); e.preventDefault() }
      else if (e.key === 'Backspace') setBuffer((b) => b.slice(0, -1))
      else if (e.key === 'ArrowDown') {
        const i = selected ? order.indexOf(selected) : -1
        setSelected(order[(i + 1) % order.length]); e.preventDefault()
      } else if (e.key === 'ArrowUp') {
        const i = selected ? order.indexOf(selected) : 0
        setSelected(order[(i - 1 + order.length) % order.length]); e.preventDefault()
      } else if (e.key === 'Enter' && selected && buffer) {
        void push('damage', { id: selected, amount: Number(buffer) }); setBuffer('')
      } else if (e.key.toLowerCase() === 'h' && selected && buffer) {
        void push('heal', { id: selected, amount: Number(buffer) }); setBuffer('')
      } else if (e.key === ' ') { void push('next_turn', {}); e.preventDefault() }
      else if (e.key.toLowerCase() === 'u' && meta.can_undo) void doUndo()
      else if (e.key.toLowerCase() === 'r' && meta.can_redo) void doRedo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state, meta, selected, buffer, push, doUndo, doRedo])

  // The selection defaults to whoever's turn it is: it snaps to the active combatant each
  // time the turn advances, but a manual click can inspect anyone until the next turn.
  const currentId = state ? state.order[state.turn_index] ?? null : null
  useEffect(() => {
    if (currentId) setSelected(currentId)
  }, [currentId])

  if (!state) {
    return (
      <>
        <h2>Combat</h2>
        <div className="card row">
          <select value={pick} onChange={(e) => setPick(e.target.value)} style={{ flex: 1 }}>
            <option value="">Choose an encounter…</option>
            {encounters?.map((e) => <option key={e.id} value={e.id}>{e.name}</option>)}
          </select>
          <button disabled={!pick} onClick={() => void begin()}>Start combat</button>
        </div>
      </>
    )
  }

  const current = currentId
  const sel = selected ? state.combatants[selected] : null
  const selBlockId = selected ? blocks[selected] : undefined

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Combat — Round {state.round}</h2>
        <div className="row" style={{ gap: 6 }}>
          <button disabled={!meta.can_undo} onClick={() => void doUndo()}>Undo</button>
          <button disabled={!meta.can_redo} onClick={() => void doRedo()}>Redo</button>
          {meta.status === 'active'
            ? <button className="danger-btn" onClick={() => void finish()}>End</button>
            : <button onClick={newCombat}>New combat</button>}
        </div>
      </div>
      <p className="muted combat-hint">↑/↓ select · digits + Enter = damage · h = heal · Space = next turn · u/r = undo/redo</p>
      {summary && <p className="muted">{summary}</p>}

      <div className="combat-grid">
        <ul className="initiative-rail">
          {state.order.map((id) => {
            const c = state.combatants[id]
            return (
              <li
                key={id}
                className={
                  'combatant-card' + (id === current ? ' current' : '') +
                  (id === selected ? ' selected' : '') + (c.defeated ? ' defeated' : '') +
                  ` side-${c.side}`
                }
                onClick={() => setSelected(id)}
              >
                <div className="cc-top">
                  <span className="cc-init">{c.initiative}</span>
                  <span className="cc-name">{c.name}</span>
                  {c.concentrating && <span className="cc-conc" title="concentrating">◎</span>}
                </div>
                <div className="hp-bar">
                  <div className="hp-fill" style={{ width: `${Math.round((c.hp / c.max_hp) * 100)}%` }} />
                  <span className="hp-text">{c.hp}/{c.max_hp}{c.temp_hp ? ` (+${c.temp_hp})` : ''}</span>
                </div>
                {c.conditions.length > 0 && (
                  <div className="cc-conditions">
                    {c.conditions.map((cond) => <span key={cond} className="tag">{cond}</span>)}
                  </div>
                )}
              </li>
            )
          })}
        </ul>

        <div className="combat-side">
          <div className="card">
            <div className="keypad-buffer">Damage/heal: <b>{buffer || '—'}</b></div>
            <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
              <button disabled={!sel || !buffer} onClick={() => { if (sel) void push('damage', { id: sel.id, amount: Number(buffer) }); setBuffer('') }}>Damage</button>
              <button disabled={!sel || !buffer} onClick={() => { if (sel) void push('heal', { id: sel.id, amount: Number(buffer) }); setBuffer('') }}>Heal</button>
              <button onClick={() => void push('next_turn', {})}>Next turn</button>
            </div>
          </div>

          {sel && (
            <div className="card">
              <h4 style={{ marginTop: 0 }}>{sel.name}</h4>
              <button onClick={() => void push('set_concentration', { id: sel.id, on: !sel.concentrating })}>
                {sel.concentrating ? 'Break concentration' : 'Concentrate'}
              </button>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                {CONDITIONS.map((cond) => {
                  const on = sel.conditions.includes(cond)
                  return (
                    <button
                      key={cond}
                      className={on ? '' : 'ghost'}
                      onClick={() => void push(on ? 'remove_condition' : 'add_condition', { id: sel.id, condition: cond })}
                    >
                      {cond}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {sel && selBlockId && campaignId && (
            <div className="card combat-statblock">
              <CombatantStatBlock campaignId={campaignId} systemId={systemId} blockId={selBlockId} />
            </div>
          )}
          {sel && !selBlockId && (
            <p className="muted" style={{ fontSize: 12 }}>No stat block linked to {sel.name}.</p>
          )}
        </div>
      </div>
    </>
  )
}

// Fetches and renders the selected combatant's stat block (defaults to the active turn).
function CombatantStatBlock({
  campaignId,
  systemId,
  blockId,
}: {
  campaignId: string
  systemId: string | null
  blockId: string
}) {
  const { data: block } = useStatBlock(campaignId, blockId)
  if (!block) return <p className="muted">Loading stat block…</p>
  return <StatBlockView systemId={systemId} block={block} />
}
