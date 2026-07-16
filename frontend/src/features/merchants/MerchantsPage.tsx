import { useState } from 'react'
import {
  useMerchants,
  useCreateMerchant,
  useDeleteMerchant,
  useMerchantStock,
  useAddStock,
  useRemoveStock,
  useBuyItem,
  useSellItem,
  useEntities,
  useEquipmentLibrary,
  useParty,
  useItems,
  type Merchant,
  type StockLine,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { Tabs, TabPanel } from '../../components/Tabs'

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

// ── Create merchant ───────────────────────────────────────────────────────────

function NewMerchantForm({ campaignId, onCreated }: { campaignId: string; onCreated: (id: string) => void }) {
  const create = useCreateMerchant(campaignId)
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const [name, setName] = useState('')
  const [npcId, setNpcId] = useState('')
  const [locationId, setLocationId] = useState('')
  const [buyback, setBuyback] = useState('50')

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(
      {
        name: name.trim(),
        npc_id: npcId || null,
        location_id: locationId || null,
        buyback_pct: Number(buyback) || 0,
      },
      {
        onSuccess: (m) => { setName(''); setNpcId(''); setLocationId(''); onCreated(m.entity_id) },
      },
    )
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 12 }}>
      <h4 style={{ marginTop: 0 }}>New shop</h4>
      <label className="field" style={{ marginBottom: 8 }}>
        <span className="muted">Name</span>
        <input placeholder="e.g. Bildrath's Mercantile" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="field" style={{ marginBottom: 8 }}>
        <span className="muted">Shopkeeper (NPC)</span>
        <select value={npcId} onChange={(e) => setNpcId(e.target.value)}>
          <option value="">— none —</option>
          {npcs?.map((n) => <option key={n.id} value={n.id}>{n.name}</option>)}
        </select>
      </label>
      <label className="field" style={{ marginBottom: 8 }}>
        <span className="muted">Storefront (location)</span>
        <select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
          <option value="">— none —</option>
          {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
        </select>
      </label>
      <label className="field-inline" style={{ marginBottom: 8 }}>
        <span className="muted">Buyback %</span>
        <input type="number" min="0" max="200" style={{ width: 70 }} value={buyback}
          onChange={(e) => setBuyback(e.target.value)} />
      </label>
      <div>
        <button type="submit" disabled={!name.trim() || create.isPending}>
          {create.isPending ? 'Creating…' : 'Create shop'}
        </button>
        {create.isError && <span className="muted" style={{ marginLeft: 8, color: 'var(--color-danger, #e53e3e)' }}>{errorText(create.error)}</span>}
      </div>
    </form>
  )
}

// ── Buy tab ────────────────────────────────────────────────────────────────────

function BuyRow({ campaignId, merchantId, line }: { campaignId: string; merchantId: string; line: StockLine }) {
  const buy = useBuyItem(campaignId, merchantId)
  const [qty, setQty] = useState('1')
  const soldOut = line.quantity === 0

  return (
    <li style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap' }}>
      {line.item_type === 'magical' && <span title="Magical">✨</span>}
      <span style={{ flex: '1 1 160px', fontWeight: 500 }}>{line.name}</span>
      {line.rarity && <span className="badge" style={{ fontSize: 11 }}>{line.rarity.replace('_', ' ')}</span>}
      <span className="badge" style={{ fontSize: 12 }}>{line.price_label}</span>
      <span className="muted" style={{ fontSize: 12, minWidth: 60 }}>
        {line.quantity === null ? 'in stock' : `${line.quantity} left`}
      </span>
      <input type="number" min="1" value={qty} onChange={(e) => setQty(e.target.value)} style={{ width: 52 }} aria-label={`quantity of ${line.name}`} />
      <button
        style={{ fontSize: 12, padding: '2px 10px' }}
        disabled={buy.isPending || soldOut}
        onClick={() => buy.mutate({ lineId: line.id, quantity: Math.max(1, Number(qty) || 1) })}
      >
        {buy.isPending ? '…' : 'Buy'}
      </button>
      {buy.isError && <span className="muted" style={{ fontSize: 11, color: 'var(--color-danger, #e53e3e)', flexBasis: '100%' }}>{errorText(buy.error)}</span>}
    </li>
  )
}

function BuyTab({ campaignId, merchantId }: { campaignId: string; merchantId: string }) {
  const { data: stock, isLoading, isError, error } = useMerchantStock(campaignId, merchantId)
  if (isLoading) return <p className="muted">Loading…</p>
  if (isError) return <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>{errorText(error)}</p>
  if (!stock?.length) return <p className="muted">Nothing for sale yet. Add stock in the Manage tab.</p>
  return (
    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
      {stock.map((line) => <BuyRow key={line.id} campaignId={campaignId} merchantId={merchantId} line={line} />)}
    </ul>
  )
}

// ── Sell tab ────────────────────────────────────────────────────────────────────

function SellTab({ campaignId, merchantId, buyback }: { campaignId: string; merchantId: string; buyback: number }) {
  const { data: items, isLoading } = useItems(campaignId, { holder_type: 'party' })
  const sell = useSellItem(campaignId, merchantId)

  if (isLoading) return <p className="muted">Loading…</p>
  if (!items?.length) return <p className="muted">The party is carrying nothing to sell.</p>
  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>The shop pays {buyback}% of an item's value.</p>
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {items.map((item) => (
          <li key={item.item_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap' }}>
            {item.item_type === 'magical' && <span title="Magical">✨</span>}
            <span style={{ flex: '1 1 160px', fontWeight: 500 }}>
              {item.instance_label ? `${item.equipment_name} · ${item.instance_label}` : item.equipment_name}
            </span>
            {item.value_gp && <span className="muted" style={{ fontSize: 12 }}>⚖ {item.value_gp}</span>}
            <button style={{ fontSize: 12, padding: '2px 10px' }} disabled={sell.isPending}
              onClick={() => { if (confirm(`Sell ${item.equipment_name} to the shop?`)) sell.mutate(item.item_id) }}>
              {sell.isPending ? '…' : 'Sell'}
            </button>
          </li>
        ))}
      </ul>
      {sell.isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>{errorText(sell.error)}</p>}
    </>
  )
}

// ── Manage tab ────────────────────────────────────────────────────────────────

function ManageTab({ campaignId, merchantId }: { campaignId: string; merchantId: string }) {
  const { data: stock } = useMerchantStock(campaignId, merchantId)
  const { data: library } = useEquipmentLibrary()
  const add = useAddStock(campaignId, merchantId)
  const remove = useRemoveStock(campaignId, merchantId)
  const [libraryId, setLibraryId] = useState('')
  const [price, setPrice] = useState('')
  const [qty, setQty] = useState('')

  const stockedLibIds = new Set((stock ?? []).map((s) => s.library_id))
  const available = (library ?? []).filter((e) => !stockedLibIds.has(e.id))

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!libraryId) return
    add.mutate(
      { library_id: libraryId, price: price.trim() || null, quantity: qty.trim() ? Number(qty) : null },
      { onSuccess: () => { setLibraryId(''); setPrice(''); setQty('') } },
    )
  }

  return (
    <>
      <form className="card" onSubmit={submit} style={{ marginBottom: 12 }}>
        <h4 style={{ marginTop: 0 }}>Add stock from library</h4>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field" style={{ flex: '2 1 200px' }}>
            <span className="muted">Item</span>
            <select value={libraryId} onChange={(e) => setLibraryId(e.target.value)}>
              <option value="">— choose a template —</option>
              {available.map((e) => <option key={e.id} value={e.id}>{e.name}{e.value_gp ? ` (${e.value_gp})` : ''}</option>)}
            </select>
          </label>
          <label className="field" style={{ flex: '1 1 100px' }}>
            <span className="muted">Price (optional)</span>
            <input placeholder="e.g. 20 gp" value={price} onChange={(e) => setPrice(e.target.value)} />
          </label>
          <label className="field" style={{ flex: '1 1 90px' }}>
            <span className="muted">Qty (blank = ∞)</span>
            <input type="number" min="0" value={qty} onChange={(e) => setQty(e.target.value)} />
          </label>
          <button type="submit" disabled={!libraryId || add.isPending}>{add.isPending ? 'Adding…' : 'Add'}</button>
        </div>
        {add.isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)', margin: '8px 0 0' }}>{errorText(add.error)}</p>}
      </form>

      {!stock?.length && <p className="muted">No stock yet.</p>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {stock?.map((line) => (
          <li key={line.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0', borderBottom: '1px solid var(--color-border)' }}>
            <span style={{ flex: 1 }}>{line.name}</span>
            <span className="badge" style={{ fontSize: 12 }}>{line.price_label}</span>
            <span className="muted" style={{ fontSize: 12 }}>{line.quantity === null ? '∞' : line.quantity}</span>
            <button className="ghost tag-x" title="Remove from shop" onClick={() => remove.mutate(line.id)}>×</button>
          </li>
        ))}
      </ul>
    </>
  )
}

// ── Selected merchant ───────────────────────────────────────────────────────────

function MerchantView({ campaignId, merchant, onDeleted }: { campaignId: string; merchant: Merchant; onDeleted: () => void }) {
  const { data: party } = useParty(campaignId)
  const del = useDeleteMerchant(campaignId)
  const [tab, setTab] = useState('buy')
  const wealthLabel = party?.wealth_label ?? '0 gp'

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h3 style={{ margin: 0 }}>{merchant.name}</h3>
          <div className="row" style={{ gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
            {merchant.npc_name && <span className="badge" style={{ fontSize: 11 }}>🧑 {merchant.npc_name}</span>}
            {merchant.location_name && <span className="badge" style={{ fontSize: 11 }}>📍 {merchant.location_name}</span>}
            <span className="badge" style={{ fontSize: 11 }}>buyback {merchant.buyback_pct}%</span>
          </div>
        </div>
        <div className="row" style={{ gap: 10, alignItems: 'center' }}>
          <span className="badge" title="Party wealth" style={{ fontSize: 13 }}>🪙 {wealthLabel}</span>
          <button className="ghost tag-x" title="Delete shop"
            onClick={() => { if (confirm(`Delete ${merchant.name}?`)) del.mutate(merchant.entity_id, { onSuccess: onDeleted }) }}>×</button>
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        <Tabs
          idPrefix="merchant"
          tabs={[{ id: 'buy', label: 'Buy' }, { id: 'sell', label: 'Sell' }, { id: 'manage', label: 'Manage' }]}
          activeTab={tab}
          onChange={setTab}
        >
          <TabPanel id="buy" activeTab={tab} idPrefix="merchant"><BuyTab campaignId={campaignId} merchantId={merchant.entity_id} /></TabPanel>
          <TabPanel id="sell" activeTab={tab} idPrefix="merchant"><SellTab campaignId={campaignId} merchantId={merchant.entity_id} buyback={merchant.buyback_pct} /></TabPanel>
          <TabPanel id="manage" activeTab={tab} idPrefix="merchant"><ManageTab campaignId={campaignId} merchantId={merchant.entity_id} /></TabPanel>
        </Tabs>
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function MerchantsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: merchants, isLoading } = useMerchants(campaignId)
  const [selected, setSelected] = useState<string | null>(null)

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const current = merchants?.find((m) => m.entity_id === selected) ?? null

  return (
    <>
      <h2>Merchants</h2>
      <div className="sheet-layout" style={{ marginTop: 12 }}>
        <div className="sheet-list" style={{ minWidth: 220 }}>
          <NewMerchantForm campaignId={campaign.id} onCreated={setSelected} />
          {isLoading && <p className="muted">Loading…</p>}
          {merchants?.length === 0 && !isLoading && <p className="muted">No shops yet. Create one above.</p>}
          <ul className="entities" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {merchants?.map((m) => (
              <li key={m.entity_id} className={selected === m.entity_id ? 'active-row' : ''}>
                <button className="linkish" style={{ textAlign: 'left', width: '100%' }} onClick={() => setSelected(m.entity_id)}>
                  {m.name} <span className="muted" style={{ fontSize: 11 }}>({m.stock_count})</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          {current
            ? <MerchantView campaignId={campaign.id} merchant={current} onDeleted={() => setSelected(null)} />
            : <p className="muted">Select a shop to view its wares.</p>}
        </div>
      </div>
    </>
  )
}
