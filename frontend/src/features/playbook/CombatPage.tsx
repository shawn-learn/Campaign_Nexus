import { useCallback, useEffect, useRef, useState } from 'react'
import {
  useCombat,
  useCombatAction,
  useCombatRedo,
  useCombatUndo,
  useCancelCombat,
  useConditions,
  useEncounters,
  useEndCombat,
  useOpenCombats,
  useRollDeathSave,
  useStartCombat,
  useStatBlock,
  type CombatActionType,
  type CombatSummary,
  type DeathSaveRules,
} from '../../api/hooks'
import type { Combatant, CombatState } from '../../lib/combatReducer'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { StatBlockView } from '../rules/StatBlockView'
import { AddCombatantDialog } from './AddCombatantDialog'
import { AttackPanel } from './AttackPanel'
import { CombatSetup } from './CombatSetup'
import { RollLog } from './RollLog'

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
  //: The concentration question raised by the last damage, waiting on the GM's answer.
  const [concentration, setConcentration] = useState<
    { id: string; name: string; dc: number } | null
  >(null)

  const storageKey = campaignId ? `nexus.combat.${campaignId}` : null

  // Resume after a refresh: the id is the only thing worth keeping, since the state folds
  // on the server anyway.
  useEffect(() => {
    if (!campaignId || !storageKey || runId) return
    const saved = localStorage.getItem(storageKey)
    if (saved) setRunId(saved)
  }, [campaignId, storageKey, runId])

  // …and resume from the server when there is no local pointer at all. localStorage was
  // the only way back into a fight, so clearing it (or opening the app in another browser)
  // stranded the run: the tracker offered a fresh encounter while the campaign stayed
  // pinned to combat mode, with no way to reach the fight and end it.
  const openRuns = useOpenCombats(campaignId, !runId)
  //: Ids that failed to load. Without this, adopting one whose GET 404s would clear it and
  //  adopt it again off the same cached list, forever.
  const dead = useRef<Set<string>>(new Set())
  useEffect(() => {
    if (runId) return
    const live = openRuns.data?.find((r) => !dead.current.has(r.run_id))
    if (!live) return
    setRunId(live.run_id)
    if (storageKey) localStorage.setItem(storageKey, live.run_id)
  }, [openRuns.data, runId, storageKey])

  const run = useCombat(campaignId, runId)
  const start = useStartCombat(campaignId ?? '')
  const action = useCombatAction(campaignId ?? '', runId)
  const undo = useCombatUndo(campaignId ?? '', runId)
  const redo = useCombatRedo(campaignId ?? '', runId)
  const end = useEndCombat(campaignId ?? '', runId)
  const cancel = useCancelCombat(campaignId ?? '', runId)

  // A saved id that no longer loads is a dead pointer — drop it rather than wedge the page.
  useEffect(() => {
    if (run.isError && storageKey) {
      if (runId) dead.current.add(runId)
      localStorage.removeItem(storageKey)
      setRunId(null)
    }
  }, [run.isError, storageKey, runId])

  const state = (run.data?.state ?? null) as CombatState | null
  const status = run.data?.status ?? 'active'
  const canUndo = run.data?.can_undo ?? false
  const canRedo = run.data?.can_redo ?? false
  const blocks = run.data?.combatant_blocks ?? {}
  // Environmental "lair" combatants carry their action text here instead of a stat block.
  const environments = run.data?.combatant_environments ?? {}
  // Whether this system has death saves at all, and what settles one. Nimble says no, and
  // the row simply never appears.
  const deathRules = run.data?.death_saves ?? { supported: false }

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

  // Drop the run and everything hanging off it, so the page falls back to the encounter
  // picker. The summary is separate: ending keeps it, cancelling and starting over don't.
  const clearRun = useCallback(() => {
    if (storageKey) localStorage.removeItem(storageKey)
    setRunId(null)
    setSelected(null)
    setBuffer('')
    setConcentration(null)
  }, [storageKey])

  const newCombat = () => {
    clearRun()
    setSummary(null)
  }

  const push = useCallback(
    (type: CombatActionType, payload: Record<string, unknown>) => {
      if (!campaignId || !runId || !state) return
      action.mutate({ type, payload })

      // Damage on a concentrating caster raises a question the GM would otherwise have to
      // remember to ask. Intercepting here catches every route to it — the keypad, the
      // button, and an applied attack roll — rather than each call site separately.
      if (type !== 'damage') return
      const c = state.combatants[String(payload.id)]
      const amount = Number(payload.amount) || 0
      if (!c?.concentrating || amount <= 0) return
      const absorbed = Math.min(c.temp_hp, amount)
      // Dropping to 0 breaks concentration outright (the reducer does it), so don't ask.
      if (c.hp - (amount - absorbed) <= 0) return
      // 5e: DC 10, or half the damage taken, whichever is higher (PHB p.203).
      setConcentration({ id: c.id, name: c.name, dc: Math.max(10, Math.floor(amount / 2)) })
    },
    [campaignId, runId, state, action],
  )

  const doUndo = useCallback(() => undo.mutate(), [undo])
  const doRedo = useCallback(() => redo.mutate(), [redo])
  // Ending drops the run entirely so the page falls back to the encounter picker — the
  // summary is carried over so the fight's outcome survives the reset.
  const finish = () =>
    end.mutate(undefined, {
      onSuccess: (s) => {
        setSummary(s)
        clearRun()
      },
    })

  // Calling it off, as opposed to ending it: the run closes without a summary, the clock
  // rewinds, and the campaign goes back to exploration. Confirmed because it throws away
  // the fight — everything that happened in it goes unrecorded.
  const abandon = useCallback(() => {
    if (!confirm('Cancel this combat? Nothing that happened in it will be recorded.')) return
    cancel.mutate(undefined, {
      onSuccess: () => {
        setSummary(null)
        clearRun()
      },
    })
  }, [cancel, clearRun])

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
    // Don't offer a fresh encounter while we're still asking whether one is already
    // running — picking one here is how a campaign ends up with two open runs.
    if (openRuns.isLoading) {
      return (
        <>
          <h2>Combat</h2>
          <p className="muted">Looking for a combat in progress…</p>
        </>
      )
    }
    return (
      <>
        <h2>Combat</h2>
        {summary && (
          <p className="muted">
            Combat ended after {summary.rounds} round(s); {summary.defeated.length} foe(s) defeated.
          </p>
        )}
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
        onCancel={abandon}
        cancelling={cancel.isPending}
      />
    )
  }

  const current = currentId
  const sel = selected ? state.combatants[selected] : null
  const selBlockId = selected ? blocks[selected] : undefined
  const selEnv = selected ? environments[selected] : undefined
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
          {status === 'active' ? (
            <>
              {/* Ending records the fight; cancelling throws it away. Both land back on
                  the encounter picker, so a wrong encounter is one click from the right one. */}
              <button className="ghost" disabled={cancel.isPending} onClick={abandon}>
                {cancel.isPending ? 'Cancelling…' : 'Cancel combat'}
              </button>
              <button className="danger-btn" disabled={end.isPending} onClick={finish}>
                {end.isPending ? 'Ending…' : 'End'}
              </button>
            </>
          ) : (
            <button onClick={newCombat}>New combat</button>
          )}
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
                  ` side-${c.side} kind-${c.kind}`
                }
                onClick={() => setSelected(id)}
              >
                <div className="cc-top">
                  <span className="cc-init">{c.initiative}</span>
                  <span className="cc-name">{c.name}</span>
                  {bloodied && <span className="cc-bloodied" title="bloodied">◆</span>}
                  {c.concentrating && <span className="cc-conc" title="concentrating">◎</span>}
                  {/* The pool on the rail, so you can see what a boss has left without
                      selecting it. */}
                  {c.legendary.max > 0 && (
                    <span
                      className="legendary-orbs"
                      title={`${c.legendary.remaining} of ${c.legendary.max} legendary actions`}
                    >
                      {Array.from({ length: c.legendary.max }, (_, i) => (
                        <span key={i} className={'orb' + (i < c.legendary.remaining ? ' on' : '')} />
                      ))}
                    </span>
                  )}
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

          {/* The concentration question, raised the moment damage lands. The player rolls
              their own save, so what the GM needs is the DC and somewhere to put the answer. */}
          {concentration && (
            <div className="card roll-card">
              <b>{concentration.name} is concentrating</b>
              <div>
                CON save <span className="roll-total">DC {concentration.dc}</span>
              </div>
              <div className="row" style={{ gap: 6, marginTop: 8 }}>
                <button onClick={() => setConcentration(null)}>Held</button>
                <button
                  className="danger-btn"
                  onClick={() => {
                    push('set_concentration', { id: concentration.id, on: false })
                    setConcentration(null)
                  }}
                >
                  Broken
                </button>
              </div>
            </div>
          )}

          {sel && (
            <div className="card">
              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
                <h4 style={{ margin: 0 }}>{sel.name}</h4>
                <button className="linkish" style={{ color: 'var(--danger)' }} onClick={removeSelected}>
                  Remove
                </button>
              </div>

              {deathRules.supported && sel.hp === 0 && sel.kind !== 'lair' && campaignId && runId && (
                <DeathSaveRow
                  campaignId={campaignId}
                  runId={runId}
                  combatant={sel}
                  rules={deathRules}
                />
              )}
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

          {sel && campaignId && runId && (
            <AttackPanel
              campaignId={campaignId}
              runId={runId}
              attackerId={sel.id}
              state={state}
              onApply={push}
            />
          )}

          {campaignId && runId && <RollLog campaignId={campaignId} runId={runId} state={state} />}

          {sel && selBlockId && campaignId && (
            <div className="card combat-statblock">
              <CombatantStatBlock campaignId={campaignId} systemId={systemId} blockId={selBlockId} />
            </div>
          )}
          {sel && selEnv && selEnv.length > 0 && (
            <div className="card">
              <h4 style={{ marginTop: 0 }}>Environmental actions</h4>
              <ul className="roster">
                {selEnv.map((a, i) => (
                  <li key={i} style={{ display: 'block' }}>
                    <b>{a.name}</b>{a.description ? ` — ${a.description}` : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {sel && !selBlockId && !selEnv && (
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

// ── Death saves ──────────────────────────────────────────────────────────────
// Shown only while a creature is at 0 hp, and only where the rule system has the mechanic.
// The pips are the point: at a table this is tracked on a scrap of paper and forgotten.
function DeathSaveRow({
  campaignId,
  runId,
  combatant,
  rules,
}: {
  campaignId: string
  runId: string
  combatant: Combatant
  rules: DeathSaveRules
}) {
  const roll = useRollDeathSave(campaignId, runId)
  const [manual, setManual] = useState('')
  const needSuccess = rules.successes ?? 3
  const needFail = rules.failures ?? 3
  const { successes, failures } = combatant.death_saves
  const stable = successes >= needSuccess
  const dead = failures >= needFail

  const manualValue = Number(manual)
  const manualValid = manual !== '' && Number.isInteger(manualValue) && manualValue >= 1 && manualValue <= 20

  const submitManual = () => {
    if (!manualValid) return
    roll.mutate({ combatantId: combatant.id, manualResult: manualValue })
    setManual('')
  }

  return (
    <div className="death-saves">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline' }}>
        <b>Dying</b>
        {stable && <span className="ds-stable">Stable</span>}
        {dead && <span className="ds-dead">Dead</span>}
      </div>
      <div className="ds-row">
        <span className="muted">Successes</span>
        <Pips filled={successes} of={needSuccess} kind="ok" />
      </div>
      <div className="ds-row">
        <span className="muted">Failures</span>
        <Pips filled={failures} of={needFail} kind="bad" />
      </div>
      {!stable && !dead && (
        <>
          <button
            style={{ marginTop: 6 }}
            disabled={roll.isPending}
            onClick={() => roll.mutate(combatant.id)}
          >
            {roll.isPending ? 'Rolling…' : `Roll ${rules.dice} vs DC ${rules.dc}`}
          </button>
          <div className="row" style={{ marginTop: 6, gap: 4, alignItems: 'center' }}>
            <span className="muted" style={{ fontSize: 12 }}>or enter a physical roll</span>
            <input
              type="number"
              min={1}
              max={20}
              value={manual}
              placeholder="d20"
              style={{ width: 56 }}
              onChange={(e) => setManual(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && submitManual()}
            />
            <button disabled={!manualValid || roll.isPending} onClick={submitManual}>
              Use
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function Pips({ filled, of, kind }: { filled: number; of: number; kind: 'ok' | 'bad' }) {
  return (
    <span className="ds-pips" aria-label={`${filled} of ${of}`}>
      {Array.from({ length: of }, (_, i) => (
        <span key={i} className={`ds-pip ${i < filled ? `on ${kind}` : ''}`} />
      ))}
    </span>
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
