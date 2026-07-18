import { useMemo, useState } from 'react'
import {
  useMerchants,
  useCreateMerchant,
  useUpdateMerchant,
  useDeleteMerchant,
  useMerchantStock,
  useAddStock,
  useUpdateStock,
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
import { ListToolbar } from '../../components/ListToolbar'
import { SearchableSelect } from '../../components/SearchableSelect'

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

const danger = { color: 'var(--color-danger, #e53e3e)' }

// ── Shop details form (shared by create + edit) ───────────────────────────────

interface ShopFields {
  name: string
  summary: string
  npcId: string
  locationId: string
  buyback: string
}

function ShopFieldset({
  campaignId, value, onChange,
}: { campaignId: string; value: ShopFields; onChange: (v: ShopFields) => void }) {
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const set = <K extends keyof ShopFields>(key: K, v: ShopFields[K]) => onChange({ ...value, [key]: v })

  return (
    <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
      <label className="field" style={{ flex: '2 1 180px' }}>
        <span className="muted">Name</span>
        <input placeholder="e.g. Bildrath's Mercantile" value={value.name}
          onChange={(e) => set('name', e.target.value)} />
      </label>
      <label className="field" style={{ flex: '2 1 180px' }}>
        <span className="muted">Summary</span>
        <input placeholder="What the shop is known for" value={value.summary}
          onChange={(e) => set('summary', e.target.value)} />
      </label>
      <label className="field" style={{ flex: '1 1 150px' }}>
        <span className="muted">Shopkeeper (NPC)</span>
        <SearchableSelect
          value={value.npcId}
          onChange={(v) => set('npcId', v)}
          options={npcs?.map((n) => ({ id: n.id, name: n.name })) ?? []}
          placeholder="— none —"
        />
      </label>
      <label className="field" style={{ flex: '1 1 150px' }}>
        <span className="muted">Storefront (location)</span>
        <SearchableSelect
          value={value.locationId}
          onChange={(v) => set('locationId', v)}
          options={locations?.map((l) => ({ id: l.id, name: l.name })) ?? []}
          placeholder="— none —"
        />
      </label>
      <label className="field" style={{ flex: '0 0 90px' }}>
        <span className="muted">Buyback %</span>
        <input type="number" min="0" max="200" value={value.buyback}
          onChange={(e) => set('buyback', e.target.value)} />
      </label>
    </div>
  )
}

const emptyShop: ShopFields = { name: '', summary: '', npcId: '', locationId: '', buyback: '50' }

// ── Create merchant ───────────────────────────────────────────────────────────

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

// ── Edit merchant ─────────────────────────────────────────────────────────────

function EditMerchantForm({
  campaignId, merchant, onDone,
}: { campaignId: string; merchant: Merchant; onDone: () => void }) {
  const update = useUpdateMerchant(campaignId)
  const [fields, setFields] = useState<ShopFields>({
    name: merchant.name,
    summary: merchant.summary ?? '',
    npcId: merchant.npc_id ?? '',
    locationId: merchant.location_id ?? '',
    buyback: String(merchant.buyback_pct),
  })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!fields.name.trim()) return
    update.mutate(
      {
        merchantId: merchant.entity_id,
        name: fields.name.trim(),
        summary: fields.summary.trim() || null,
        npc_id: fields.npcId || null,
        location_id: fields.locationId || null,
        buyback_pct: Number(fields.buyback) || 0,
        // `null` means "unchanged" to the API, so unsetting a link needs the clear flag.
        clear_npc: !fields.npcId,
        clear_location: !fields.locationId,
      },
      { onSuccess: onDone },
    )
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 12 }}>
      <h4 style={{ marginTop: 0 }}>Edit shop</h4>
      <ShopFieldset campaignId={campaignId} value={fields} onChange={setFields} />
      <div className="row" style={{ gap: 8, marginTop: 10, alignItems: 'center' }}>
        <button type="submit" disabled={!fields.name.trim() || update.isPending}>
          {update.isPending ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="ghost" onClick={onDone}>Cancel</button>
        {update.isError && <span className="muted" style={danger}>{errorText(update.error)}</span>}
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
      {buy.isError && <span className="muted" style={{ fontSize: 11, ...danger, flexBasis: '100%' }}>{errorText(buy.error)}</span>}
    </li>
  )
}

function BuyTab({ campaignId, merchantId }: { campaignId: string; merchantId: string }) {
  const { data: stock, isLoading, isError, error } = useMerchantStock(campaignId, merchantId)
  const [query, setQuery] = useState('')

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return q ? (stock ?? []).filter((l) => l.name.toLowerCase().includes(q)) : (stock ?? [])
  }, [stock, query])

  if (isLoading) return <p className="muted">Loading…</p>
  if (isError) return <p className="muted" style={danger}>{errorText(error)}</p>
  if (!stock?.length) return <p className="muted">Nothing for sale yet. Add stock in the Manage tab.</p>
  return (
    <>
      {stock.length > 8 && (
        <ListToolbar query={query} onQuery={setQuery} placeholder="Search wares…"
          count={shown.length} total={stock.length} />
      )}
      {!shown.length && <p className="muted">No wares match “{query}”.</p>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {shown.map((line) => <BuyRow key={line.id} campaignId={campaignId} merchantId={merchantId} line={line} />)}
      </ul>
    </>
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
      {sell.isError && <p className="muted" style={danger}>{errorText(sell.error)}</p>}
    </>
  )
}

// ── Manage tab ────────────────────────────────────────────────────────────────

function StockRow({ campaignId, merchantId, line }: { campaignId: string; merchantId: string; line: StockLine }) {
  const update = useUpdateStock(campaignId, merchantId)
  const remove = useRemoveStock(campaignId, merchantId)
  const [editing, setEditing] = useState(false)
  const [price, setPrice] = useState(line.price_label)
  const [qty, setQty] = useState(line.quantity === null ? '' : String(line.quantity))

  const save = () => {
    update.mutate(
      {
        lineId: line.id,
        price: price.trim() || null,
        quantity: qty.trim() ? Number(qty) : null,
        clear_quantity: !qty.trim(),
      },
      { onSuccess: () => setEditing(false) },
    )
  }

  const cancel = () => {
    setPrice(line.price_label)
    setQty(line.quantity === null ? '' : String(line.quantity))
    setEditing(false)
  }

  const rowStyle: React.CSSProperties = {
    display: 'flex', alignItems: 'center', gap: 10, padding: '6px 0',
    borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap',
  }

  if (editing) {
    return (
      <li style={rowStyle}>
        <span style={{ flex: '1 1 140px' }}>{line.name}</span>
        <input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="e.g. 20 gp"
          style={{ width: 90 }} aria-label={`price of ${line.name}`} />
        <input type="number" min="0" value={qty} onChange={(e) => setQty(e.target.value)} placeholder="∞"
          style={{ width: 64 }} aria-label={`quantity of ${line.name}`} />
        <button style={{ fontSize: 12, padding: '2px 10px' }} disabled={update.isPending} onClick={save}>
          {update.isPending ? '…' : 'Save'}
        </button>
        <button className="ghost" style={{ fontSize: 12, padding: '2px 10px' }} onClick={cancel}>Cancel</button>
        {update.isError && <span className="muted" style={{ fontSize: 11, ...danger, flexBasis: '100%' }}>{errorText(update.error)}</span>}
      </li>
    )
  }

  return (
    <li style={rowStyle}>
      <span style={{ flex: 1 }}>{line.name}</span>
      <span className="badge" style={{ fontSize: 12 }}>{line.price_label}</span>
      <span className="muted" style={{ fontSize: 12, minWidth: 24, textAlign: 'right' }}>
        {line.quantity === null ? '∞' : line.quantity}
      </span>
      <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} title="Edit price and quantity"
        onClick={() => setEditing(true)}>Edit</button>
      <button className="ghost tag-x" title="Remove from shop"
        onClick={() => { if (confirm(`Remove ${line.name} from the shop?`)) remove.mutate(line.id) }}>×</button>
    </li>
  )
}

function ManageTab({ campaignId, merchantId }: { campaignId: string; merchantId: string }) {
  const { data: stock } = useMerchantStock(campaignId, merchantId)
  const { data: library } = useEquipmentLibrary()
  const add = useAddStock(campaignId, merchantId)
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
        {add.isError && <p className="muted" style={{ ...danger, margin: '8px 0 0' }}>{errorText(add.error)}</p>}
      </form>

      {!stock?.length && <p className="muted">No stock yet.</p>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {stock?.map((line) => (
          <StockRow key={line.id} campaignId={campaignId} merchantId={merchantId} line={line} />
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
  const [editing, setEditing] = useState(false)
  const wealthLabel = party?.wealth_label ?? '0 gp'

  return (
    <div>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h3 style={{ margin: 0 }}>{merchant.name}</h3>
          {merchant.summary && <p className="muted" style={{ margin: '4px 0 0', fontSize: 13 }}>{merchant.summary}</p>}
          <div className="row" style={{ gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
            {merchant.npc_name && <span className="badge" style={{ fontSize: 11 }}>🧑 {merchant.npc_name}</span>}
            {merchant.location_name && <span className="badge" style={{ fontSize: 11 }}>📍 {merchant.location_name}</span>}
            <span className="badge" style={{ fontSize: 11 }}>buyback {merchant.buyback_pct}%</span>
          </div>
        </div>
        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
          <span className="badge" title="Party wealth" style={{ fontSize: 13 }}>🪙 {wealthLabel}</span>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 10px' }} title="Edit shop details"
            onClick={() => setEditing((v) => !v)}>{editing ? 'Close' : 'Edit'}</button>
          <button className="ghost tag-x" title="Delete shop"
            onClick={() => { if (confirm(`Delete ${merchant.name}?`)) del.mutate(merchant.entity_id, { onSuccess: onDeleted }) }}>×</button>
        </div>
      </div>

      {editing && (
        <div style={{ marginTop: 12 }}>
          {/* Keyed so switching shops while the form is open resets its fields. */}
          <EditMerchantForm key={merchant.entity_id} campaignId={campaignId} merchant={merchant}
            onDone={() => setEditing(false)} />
        </div>
      )}

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

  const current = merchants?.find((m) => m.entity_id === selected) ?? null

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <h2 style={{ margin: 0 }}>Merchants</h2>
        <button onClick={() => setCreating((v) => !v)}>{creating ? 'Cancel' : '+ New shop'}</button>
      </div>

      {creating && (
        <div style={{ marginTop: 12 }}>
          <NewMerchantForm campaignId={campaign.id}
            onCreated={(id) => { setSelected(id); setCreating(false) }}
            onCancel={() => setCreating(false)} />
        </div>
      )}

      <div className="sheet-layout" style={{ marginTop: 12 }}>
        <div className="sheet-list" style={{ minWidth: 220 }}>
          <ListToolbar query={query} onQuery={setQuery} placeholder="Search shops…"
            count={shown.length} total={merchants?.length} />
          {isLoading && <p className="muted">Loading…</p>}
          {merchants?.length === 0 && !isLoading && <p className="muted">No shops yet. Create one above.</p>}
          {!!merchants?.length && !shown.length && <p className="muted">No shops match “{query}”.</p>}
          <ul className="entities" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {shown.map((m) => (
              <li key={m.entity_id} className={selected === m.entity_id ? 'active-row' : ''}>
                <button className="linkish" style={{ textAlign: 'left', width: '100%' }} onClick={() => setSelected(m.entity_id)}>
                  <span>{m.name} <span className="muted" style={{ fontSize: 11 }}>({m.stock_count})</span></span>
                  {m.location_name && (
                    <span className="muted" style={{ display: 'block', fontSize: 11 }}>📍 {m.location_name}</span>
                  )}
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
