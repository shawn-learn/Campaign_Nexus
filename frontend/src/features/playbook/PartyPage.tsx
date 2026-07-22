import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useAddPartyMember,
  useCastPartySpell,
  useParty,
  usePatchParty,
  useRest,
  useStatBlocks,
  useItems,
  type SpellPoolOut,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useCalendar } from '../../lib/useCalendar'
import { TravelPlanner } from './TravelPlanner'
import { Tabs, TabPanel } from '../../components/Tabs'
import { SheetEditorPanel } from '../rules/SheetEditorPanel'
import type { StatBlock } from '../../api/client'

// Party tracker + plugin-driven rests (FR-7, docs/07 §9.4). A rest advances the clock and
// restores party members per the active rule system.
export function PartyPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const cal = useCalendar(campaignId)
  const { data: party } = useParty(campaignId)
  const { data: pcs } = useStatBlocks(campaignId, 'pc')
  const addMember = useAddPartyMember(campaignId ?? '')
  const patch = usePatchParty(campaignId ?? '')
  const rest = useRest(campaignId ?? '')

  const [pick, setPick] = useState('')
  const [restMsg, setRestMsg] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('party')
  const [selectedBlock, setSelectedBlock] = useState<StatBlock | null>(null)
  const { data: partyItems } = useItems(campaignId, { holder_type: 'party' })

  const memberIds = new Set(party?.members.map((m) => m.stat_block_id))
  const available = (pcs ?? []).filter((p) => !memberIds.has(p.id))

  // The rest buttons are whatever the campaign's rule system declares — 5e's short/long,
  // Nimble's field/safe — so this page never names a game system's mechanics.
  const restTypes = party?.rest_types ?? []

  const doRest = (type: string) =>
    rest.mutate(type, {
      onSuccess: (r) => {
        const to = cal ? cal.format(r.to_time).label + ' ' + cal.format(r.to_time).time : `${r.to_time}m`
        setRestMsg(`${type} rest complete — now ${to}`)
      },
    })

  return (
    <>
      <h2>
        Party
        {party?.current_location_name && (
          <span className="badge" style={{ marginLeft: 8 }}>📍 {party.current_location_name}</span>
        )}
      </h2>

      <Tabs
        tabs={[
          { id: 'party', label: 'Party' },
          { id: 'inventory', label: `Inventory${partyItems?.length ? ` (${partyItems.length})` : ''}` },
          { id: 'pc-sheets', label: 'PC Sheets' },
        ]}
        activeTab={activeTab}
        onChange={setActiveTab}
      >
        <TabPanel id="party" activeTab={activeTab}>
          <div className="card row" style={{ justifyContent: 'space-between', marginTop: 12 }}>
            <WealthField
              valueCp={party?.wealth_cp ?? 0}
              label={party?.wealth_label ?? '0 gp'}
              onCommit={(wealth_cp) => patch.mutate({ wealth_cp })}
            />
            <div className="row" style={{ gap: 8 }}>
              {restTypes.map((type) => (
                <button key={type} onClick={() => doRest(type)} disabled={rest.isPending}>
                  {type} rest
                </button>
              ))}
              {restTypes.length === 0 && <span className="muted">This system has no rests.</span>}
            </div>
          </div>

          {restMsg && <p className="muted">{restMsg}</p>}

          <ul className="entities" style={{ marginTop: 16 }}>
            {party?.members.map((m) => (
              <li key={m.stat_block_id}>
                <span>{m.name}</span>
                <span className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
                  <span className="badge">HP {m.hp} / {m.max_hp}</span>
                  {campaignId && (
                    <SlotPips
                      campaignId={campaignId}
                      statBlockId={m.stat_block_id}
                      pools={m.spell_pools ?? []}
                    />
                  )}
                </span>
              </li>
            ))}
            {party?.members.length === 0 && <p className="muted">No party members yet.</p>}
          </ul>

          <div className="card row" style={{ marginTop: 16 }}>
            <select value={pick} onChange={(e) => setPick(e.target.value)} style={{ flex: 1 }}>
              <option value="">Add a PC…</option>
              {available.map((p) => (
                <option key={p.id} value={p.id}>{p.label || '(untitled)'}</option>
              ))}
            </select>
            <button
              disabled={!pick || addMember.isPending}
              onClick={() => { if (pick) { addMember.mutate(pick); setPick('') } }}
            >
              Add
            </button>
          </div>

          {campaign && <div style={{ marginTop: 16 }}><TravelPlanner campaignId={campaign.id} systemId={campaign.rule_system_id} /></div>}
        </TabPanel>

        <TabPanel id="inventory" activeTab={activeTab}>
          <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginTop: 12, marginBottom: 8 }}>
            <h3 style={{ margin: 0 }}>Party Inventory</h3>
            <Link to="/equipment" style={{ fontSize: 13 }}>Manage in Equipment →</Link>
          </div>
          {!partyItems?.length && (
            <p className="muted">The party carries nothing. Use the Equipment page to assign items.</p>
          )}
          <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
            {partyItems?.map((item) => (
              <li
                key={item.item_id}
                className="row"
                style={{ gap: 8, padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}
              >
                {item.item_type === 'magical' && <span title="Magical">✨</span>}
                <Link
                  className="linkish"
                  to="/entities/$entityId"
                  params={{ entityId: item.equipment_id }}
                  style={{ flex: 1 }}
                >
                  {item.instance_label ? `${item.equipment_name} · ${item.instance_label}` : item.equipment_name}
                </Link>
                {item.rarity && (
                  <span className="badge" style={{ fontSize: 11 }}>
                    {item.rarity.replace('_', ' ')}
                  </span>
                )}
                {item.requires_attunement && (
                  <span className="badge" style={{ fontSize: 11 }}>🔮 attune</span>
                )}
                {item.value_gp && (
                  <span className="muted" style={{ fontSize: 12 }}>⚖ {item.value_gp}</span>
                )}
                {item.current_location_name && (
                  <span className="badge" style={{ fontSize: 11 }}>📍 {item.current_location_name}</span>
                )}
              </li>
            ))}
          </ul>
        </TabPanel>

        <TabPanel id="pc-sheets" activeTab={activeTab}>
          {campaignId && campaign?.rule_system_id && (
            <div className="sheet-layout" style={{ marginTop: 12 }}>
              <ul className="entities sheet-list">
                {pcs?.map((p) => (
                  <li key={p.id} className={selectedBlock?.id === p.id ? 'active-row' : ''}>
                    <button className="linkish" onClick={() => setSelectedBlock(p)}>
                      {p.label || '(untitled)'}
                    </button>
                  </li>
                ))}
                {pcs?.length === 0 && <p className="muted">No PC sheets yet.</p>}
                <button
                  style={{ marginTop: 12, width: '100%' }}
                  onClick={() => setSelectedBlock(null)}
                >
                  + New PC Sheet
                </button>
              </ul>

              <div style={{ flex: 1 }}>
                <SheetEditorPanel
                  key={selectedBlock?.id ?? `new-pc`}
                  campaignId={campaignId}
                  systemId={campaign.rule_system_id}
                  sheetType="pc"
                  existing={selectedBlock}
                  onSaved={(b) => setSelectedBlock(b)}
                />
              </div>
            </div>
          )}
        </TabPanel>
      </Tabs>
    </>
  )
}

// Spell slots away from the combat tracker — the wizard who casts *identify* over
// breakfast. Click a lit pip to spend it, a spent one to hand it back; the rest buttons
// above restore them per the rule system's own recharge rules, so nothing here knows what
// a short rest is. Renders nothing at all for a character who doesn't cast.
function SlotPips({
  campaignId,
  statBlockId,
  pools,
}: {
  campaignId: string
  statBlockId: string
  pools: SpellPoolOut[]
}) {
  const cast = useCastPartySpell(campaignId)
  if (!pools.length) return null

  return (
    <span className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
      {pools.map((pool) => (
        <span key={pool.key} className="slot-group" title={`${pool.label} — ${pool.recharge} rest`}>
          <span className="muted" style={{ fontSize: 11 }}>{pool.label}</span>
          <span className="ds-pips">
            {Array.from({ length: pool.max ?? 0 }, (_, i) => {
              const filled = i < (pool.remaining ?? 0)
              return (
                <button
                  key={i}
                  type="button"
                  className={'slot-pip' + (filled ? ' on' : '')}
                  disabled={cast.isPending}
                  aria-label={
                    filled
                      ? `Spend a ${pool.label} slot`
                      : `Restore a ${pool.label} slot`
                  }
                  onClick={() =>
                    cast.mutate({
                      statBlockId,
                      poolKey: pool.key,
                      // Clicking a lit pip spends one; clicking a spent one takes the
                      // mis-click back, which is the only undo this side of a fight has.
                      delta: filled ? -1 : 1,
                    })
                  }
                />
              )
            })}
          </span>
        </span>
      ))}
    </span>
  )
}

// Party wealth is tracked in copper; the GM edits gp/sp/cp separately. Edits
// commit on blur/Enter (not per keystroke) so typing doesn't spam PATCHes.
function WealthField({ valueCp, label, onCommit }: { valueCp: number; label: string; onCommit: (cp: number) => void }) {
  const split = (cp: number) => {
    const c = Math.max(0, cp)
    return { gp: Math.floor(c / 100), sp: Math.floor((c % 100) / 10), cp: c % 10 }
  }
  const [coins, setCoins] = useState(split(valueCp))

  // Re-sync when the server value changes (e.g. after a shop purchase).
  useEffect(() => { setCoins(split(valueCp)) }, [valueCp])

  const commit = () => {
    const next = coins.gp * 100 + coins.sp * 10 + coins.cp
    if (next !== valueCp) onCommit(next)
  }

  const field = (key: 'gp' | 'sp' | 'cp') => (
    <input
      type="number" min="0" style={{ width: 56 }} aria-label={key}
      value={coins[key]}
      onChange={(e) => setCoins((c) => ({ ...c, [key]: Math.max(0, Number(e.target.value) || 0) }))}
      onBlur={commit}
      onKeyDown={(e) => { if (e.key === 'Enter') e.currentTarget.blur() }}
    />
  )

  return (
    <div className="row muted" style={{ gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
      <span title="Party wealth">🪙 {label}</span>
      <span style={{ opacity: 0.6 }}>·</span>
      {field('gp')}<span>gp</span>
      {field('sp')}<span>sp</span>
      {field('cp')}<span>cp</span>
    </div>
  )
}
