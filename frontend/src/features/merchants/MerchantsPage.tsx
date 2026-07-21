// Index of shops. Running a shop (buy/sell/stock) happens on its wiki entity
// page — see EntityDetailPage's `merchant` branch — so rows link there.
import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useMerchants, useCreateMerchant } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { ListToolbar } from '../../components/ListToolbar'
import { ShopFieldset, emptyShop, type ShopFields } from './ShopFieldset'
import { errorText, danger } from './ShopTabs'

function NewMerchantForm({
  campaignId, onCreated, onCancel,
}: { campaignId: string; onCreated: (id: string) => void; onCancel: () => void }) {
  const create = useCreateMerchant(campaignId)
  const [fields, setFields] = useState<ShopFields>(emptyShop)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!fields.name.trim()) return
    create.mutate(
      {
        name: fields.name.trim(),
        summary: fields.summary.trim() || null,
        npc_id: fields.npcId || null,
        location_id: fields.locationId || null,
        buyback_pct: Number(fields.buyback) || 0,
      },
      { onSuccess: (m) => { setFields(emptyShop); onCreated(m.entity_id) } },
    )
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 12 }}>
      <h4 style={{ marginTop: 0 }}>New shop</h4>
      <ShopFieldset campaignId={campaignId} value={fields} onChange={setFields} />
      <div className="row" style={{ gap: 8, marginTop: 10, alignItems: 'center' }}>
        <button type="submit" disabled={!fields.name.trim() || create.isPending}>
          {create.isPending ? 'Creating…' : 'Create shop'}
        </button>
        <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
        {create.isError && <span className="muted" style={danger}>{errorText(create.error)}</span>}
      </div>
    </form>
  )
}

export function MerchantsPage() {
  const { campaign } = useActiveCampaign()
  const navigate = useNavigate()
  const campaignId = campaign?.id ?? null
  const { data: merchants, isLoading } = useMerchants(campaignId)
  const [creating, setCreating] = useState(false)
  const [query, setQuery] = useState('')

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return merchants ?? []
    return (merchants ?? []).filter((m) =>
      [m.name, m.npc_name, m.location_name].some((s) => s?.toLowerCase().includes(q)),
    )
  }, [merchants, query])

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const openShop = (entityId: string) =>
    navigate({ to: '/entities/$entityId', params: { entityId }, search: { tab: 'buy' } })

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <h2 style={{ margin: 0 }}>Merchants</h2>
        <button onClick={() => setCreating((v) => !v)}>{creating ? 'Cancel' : '+ New shop'}</button>
      </div>

      {creating && (
        <div style={{ marginTop: 12 }}>
          <NewMerchantForm campaignId={campaign.id}
            onCreated={(id) => { setCreating(false); openShop(id) }}
            onCancel={() => setCreating(false)} />
        </div>
      )}

      <div style={{ marginTop: 12 }}>
        <ListToolbar query={query} onQuery={setQuery} placeholder="Search shops…"
          count={shown.length} total={merchants?.length} />
        {isLoading && <p className="muted">Loading…</p>}
        {merchants?.length === 0 && !isLoading && <p className="muted">No shops yet. Create one above.</p>}
        {!!merchants?.length && !shown.length && <p className="muted">No shops match “{query}”.</p>}
        <ul className="entities" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {shown.map((m) => (
            <li key={m.entity_id}>
              <button className="linkish" style={{ textAlign: 'left', width: '100%' }}
                onClick={() => openShop(m.entity_id)}>
                <span>{m.name} <span className="muted" style={{ fontSize: 11 }}>({m.stock_count} in stock)</span></span>
                <span className="muted" style={{ display: 'block', fontSize: 11 }}>
                  {m.location_name && <>📍 {m.location_name}</>}
                  {m.location_name && m.npc_name && ' · '}
                  {m.npc_name && <>🧑 {m.npc_name}</>}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  )
}
