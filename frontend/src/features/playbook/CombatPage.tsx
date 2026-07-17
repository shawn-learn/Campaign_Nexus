import { useCallback, useEffect, useState } from 'react'
import {
  useCombat,
  useCombatAction,
  useCombatRedo,
  useCombatUndo,
  useConditions,
  useEncounters,
  useEndCombat,
  useStartCombat,
  useStatBlock,
  type CombatActionType,
  type CombatSummary,
} from '../../api/hooks'
import type { CombatState } from '../../lib/combatReducer'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { StatBlockView } from '../rules/StatBlockView'
import { AddCombatantDialog } from './AddCombatantDialog'
import { CombatSetup } from './CombatSetup'

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

// Combat tracker (FR-12.3, ADR-005). Keyboard-first: ↑/↓ select, digits build a number,
// Enter = damage, h = heal, Space = next turn, u/r = undo/redo. Optimistic via the TS
// reducer twin so each action feels instant (NFR-1.3), reconciled with the server's fold.
//
// Only the run *id* is local; the folded state lives in the query cache. That is what lets a
// failed action roll back to the server's truth rather than stranding a wound on screen that
// was never recorded.
export function CombatPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const systemId = campaign?.rule_system_id ?? null
  const { data: encounters } = useEncounters(campaignId)
  const { data: conditions } = useConditions(systemId)

  const [pick, setPick] = useState('')
  const [runId, setRunId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [buffer, setBuffer] = useState('')
  const [summary, setSummary] = useState<CombatSummary | null>(null)
  const [addOpen, setAddOpen] = useState(false)

  const storageKey = campaignId ? `nexus.combat.${campaignId}` : null

  // Resume after a refresh: the id is the only thing worth keeping, since the state folds
  // on the server anyway.
  useEffect(() => {
    if (!campaignId || !storageKey || runId) return
    const saved = localStorage.getItem(storageKey)
    if (saved) setRunId(saved)
  }, [campaignId, storageKey, runId])

  const run = useCombat(campaignId, runId)
  const start = useStartCombat(campaignId ?? '')
  const action = useCombatAction(campaignId ?? '', runId)
  const undo = useCombatUndo(campaignId ?? '', runId)
  const redo = useCombatRedo(campaignId ?? '', runId)
  const end = useEndCombat(campaignId ?? '', runId)

  // A saved id that no longer loads is a dead pointer — drop it rather than wedge the page.
  useEffect(() => {
    if (run.isError && storageKey) {
      localStorage.removeItem(storageKey)
      setRunId(null)
    }
  }, [run.isError, storageKey])

  const state = (run.data?.state ?? null) as CombatState | null
  const status = run.data?.status ?? 'active'
  const canUndo = run.data?.can_undo ?? false
  const canRedo = run.data?.can_redo ?? false
  const blocks = run.data?.combatant_blocks ?? {}

  const begin = () => {
    if (!campaignId || !pick) return
    start.mutate(pick, {
      onSuccess: (r) => {
        setRunId(r.run_id)
        if (storageKey) localStorage.setItem(storageKey, r.run_id)
        setSummary(null)
      },
    })
  }

  const newCombat = () => {
    if (storageKey) localStorage.removeItem(storageKey)
    setRunId(null)
    setSelected(null)
    setSummary(null)
  }

  const push = useCallback(
    (type: CombatActionType, payload: Record<string, unknown>) => {
      if (!campaignId || !runId) return
      action.mutate({ type, payload })
    },
    [campaignId, runId, action],
  )

  const doUndo = useCallback(() => undo.mutate(), [undo])
  const doRedo = useCallback(() => redo.mutate(), [redo])
  const finish = () => end.mutate(undefined, { onSuccess: setSummary })

  const removeSelected = useCallback(() => {
    if (!state || !selected) return
    const c = state.combatants[selected]
    if (c && confirm(`Remove ${c.name} from the fight?`)) push('remove_combatant', { id: selected })
  }, [state, selected, push])

  // Keyboard controls. Everything the tracker can do has a key — the new roster actions
  // included, so adding them didn't quietly turn this into a mouse-only screen.
  useEffect(() => {
    if (!state || status !== 'active' || addOpen) return
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
        push('damage', { id: selected, amount: Number(buffer) }); setBuffer('')
      } else if (e.key.toLowerCase() === 'h' && selected && buffer) {
        push('heal', { id: selected, amount: Number(buffer) }); setBuffer('')
      } else if (e.key.toLowerCase() === 't' && selected && buffer) {
        push('set_temp_hp', { id: selected, amount: Number(buffer) }); setBuffer('')
      } else if (e.key.toLowerCase() === 'a') { setAddOpen(true); e.preventDefault() }
      else if (e.key === 'Delete' && selected) { removeSelected(); e.preventDefault() }
      else if (e.key === ' ') { push('next_turn', {}); e.preventDefault() }
      else if (e.key.toLowerCase() === 'u' && canUndo) doUndo()
      else if (e.key.toLowerCase() === 'r' && canRedo) doRedo()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [state, status, addOpen, canUndo, canRedo, selected, buffer, push, doUndo, doRedo, removeSelected])

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
          <button disabled={!pick || start.isPending} onClick={begin}>
            {start.isPending ? 'Starting…' : 'Start combat'}
          </button>
        </div>
        {run.isLoading && <p className="muted">Loading combat…</p>}
        {start.isError && (
          <p className="muted" style={{ color: 'var(--danger)' }}>
            Couldn't start combat: {errorText(start.error)}
          </p>
        )}
      </>
    )
  }

  // Roll for initiative before round 1. This lives on the run, not in local state, so a
  // refresh mid-setup comes back to the roster rather than dropping you into the fight.
  if (status === 'setup' && run.data) {
    return (
      <CombatSetup
        campaignId={campaignId!}
        run={run.data}
        onBegun={() => setSelected(state.order[0] ?? null)}
      />
    )
  }

  const current = currentId
  const sel = selected ? state.combatants[selected] : null
  const selBlockId = selected ? blocks[selected] : undefined
  // A failed action has already rolled the tracker back to the server's state; say so,
  // otherwise the GM just sees their damage silently undo itself.
  const actionError = action.isError ? action.error : undo.isError ? undo.error : redo.isError ? redo.error : null

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Combat — Round {state.round}</h2>
        <div className="row" style={{ gap: 6 }}>
          {status === 'active' && (
            <button className="ghost" onClick={() => setAddOpen(true)}>Add</button>
          )}
          <button disabled={!canUndo} onClick={doUndo}>Undo</button>
          <button disabled={!canRedo} onClick={doRedo}>Redo</button>
          {status === 'active'
            ? <button className="danger-btn" disabled={end.isPending} onClick={finish}>
                {end.isPending ? 'Ending…' : 'End'}
              </button>
            : <button onClick={newCombat}>New combat</button>}
        </div>
      </div>
      <p className="muted combat-hint">↑/↓ select · digits + Enter = damage · h = heal · t = temp HP · Space = next turn · a = add · Del = remove · u/r = undo/redo</p>
      {summary && (
        <p className="muted">
          Combat ended after {summary.rounds} round(s); {summary.defeated.length} foe(s) defeated.
        </p>
      )}
      {actionError && (
        <p className="muted" style={{ color: 'var(--danger)' }}>
          That didn't stick: {errorText(actionError)}
        </p>
      )}

      <div className="combat-grid">
        <ul className="initiative-rail">
          {state.order.map((id) => {
            const c = state.combatants[id]
            const pct = c.max_hp > 0 ? Math.round((c.hp / c.max_hp) * 100) : 0
            // Bloodied at half — the one HP threshold a 5e table actually calls out loud,
            // and worth seeing without doing the arithmetic mid-turn.
            const bloodied = !c.defeated && c.max_hp > 0 && c.hp * 2 <= c.max_hp && c.hp > 0
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
                  {bloodied && <span className="cc-bloodied" title="bloodied">◆</span>}
                  {c.concentrating && <span className="cc-conc" title="concentrating">◎</span>}
                </div>
                <div className={'hp-bar' + (bloodied ? ' bloodied' : '')}>
                  <div className="hp-fill" style={{ width: `${pct}%` }} />
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
              <button disabled={!sel || !buffer} onClick={() => { if (sel) push('damage', { id: sel.id, amount: Number(buffer) }); setBuffer('') }}>Damage</button>
              <button disabled={!sel || !buffer} onClick={() => { if (sel) push('heal', { id: sel.id, amount: Number(buffer) }); setBuffer('') }}>Heal</button>
              <button className="ghost" disabled={!sel || !buffer} onClick={() => { if (sel) push('set_temp_hp', { id: sel.id, amount: Number(buffer) }); setBuffer('') }}>Temp HP</button>
              <button onClick={() => push('next_turn', {})}>Next turn</button>
            </div>
          </div>

          {sel && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                <h4 style={{ margin: 0 }}>{sel.name}</h4>
                <button className="linkish" style={{ color: 'var(--danger)' }} onClick={removeSelected}>
                  Remove
                </button>
              </div>
              <button
                style={{ marginTop: 8 }}
                onClick={() => push('set_concentration', { id: sel.id, on: !sel.concentrating })}
              >
                {sel.concentrating ? 'Break concentration' : 'Concentrate'}
              </button>
              {/* The rule system's own list — 5e ships 15, Nimble a different 10. Hard-coding
                  six of 5e's here meant the other nine were unreachable from the tracker. */}
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 8 }}>
                {conditions?.map((cond) => {
                  const on = sel.conditions.includes(cond.id)
                  return (
                    <button
                      key={cond.id}
                      className={on ? '' : 'ghost'}
                      title={cond.description}
                      onClick={() => push(on ? 'remove_condition' : 'add_condition', { id: sel.id, condition: cond.id })}
                    >
                      {cond.name}
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

      {addOpen && campaignId && runId && (
        <AddCombatantDialog
          campaignId={campaignId}
          runId={runId}
          onClose={() => setAddOpen(false)}
        />
      )}
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
