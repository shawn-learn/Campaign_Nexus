import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useEquipmentList,
  useCreateEquipment,
  useUpdateEquipment,
  useDeleteEquipment,
  useItems,
  useCreateItem,
  useTransferItem,
  useDeleteItem,
  useItemHistory,
  useEntities,
  useEquipmentLibrary,
  useCreateLibraryEntry,
  useDeleteLibraryEntry,
  useImportFromLibrary,
  useSaveToLibrary,
  type Equipment,
  type Item,
  type ItemFilters,
  type LibraryEntry,
  type LibraryFilters,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { Tabs, TabPanel } from '../../components/Tabs'
import { Modal } from '../../components/Modal'

const ITEM_TYPES = ['magical', 'mundane'] as const
const RARITIES = ['common', 'uncommon', 'rare', 'very_rare', 'legendary'] as const
const HOLDER_TYPES = ['party', 'pc', 'npc', 'location', 'unowned'] as const

const RARITY_COLORS: Record<string, string> = {
  common: '#9e9e9e',
  uncommon: '#4caf50',
  rare: '#2196f3',
  very_rare: '#9c27b0',
  legendary: '#ff9800',
}

function rarityLabel(r: string | null | undefined) {
  return r ? r.replace('_', ' ') : null
}

function holderLabel(item: Item) {
  if (item.current_holder_type === 'party') return '🎒 Party'
  if (item.current_holder_name) return item.current_holder_name
  if (item.current_holder_type === 'unowned' || !item.current_holder_type) return 'Unowned'
  return '—'
}

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

// ── Catalog: create definition ───────────────────────────────────────────────

function CreateEquipmentForm({ campaignId }: { campaignId: string }) {
  const create = useCreateEquipment(campaignId)
  const [name, setName] = useState('')
  const [type, setType] = useState<string>('mundane')
  const [rarity, setRarity] = useState<string>('')
  const [attunes, setAttunes] = useState(false)
  const [valueGp, setValueGp] = useState('')
  const [weight, setWeight] = useState('')
  const [properties, setProperties] = useState('')
  const isMagical = type === 'magical'

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(
      {
        name: name.trim(),
        item_type: type,
        // Only send rarity/attunement for magical definitions.
        rarity: isMagical ? rarity || null : null,
        requires_attunement: isMagical ? attunes : false,
        value_gp: valueGp.trim() || null,
        weight_lb: weight.trim() ? Number(weight) : null,
        properties: properties.trim() || null,
      },
      {
        onSuccess: () => {
          setName(''); setRarity(''); setAttunes(false)
          setValueGp(''); setWeight(''); setProperties('')
        },
      },
    )
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 16 }}>
      <h4 style={{ marginTop: 0 }}>New definition</h4>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label className="field" style={{ flex: '2 1 200px' }}>
          <span className="muted">Name</span>
          <input placeholder="e.g. Longsword, Sunsword…" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field" style={{ flex: '1 1 110px' }}>
          <span className="muted">Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {ITEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        {isMagical && (
          <label className="field" style={{ flex: '1 1 130px' }}>
            <span className="muted">Rarity</span>
            <select value={rarity} onChange={(e) => setRarity(e.target.value)}>
              <option value="">— none —</option>
              {RARITIES.map((r) => <option key={r} value={r}>{rarityLabel(r)}</option>)}
            </select>
          </label>
        )}
        <label className="field" style={{ flex: '1 1 100px' }}>
          <span className="muted">Value</span>
          <input placeholder="e.g. 15 gp" value={valueGp} onChange={(e) => setValueGp(e.target.value)} />
        </label>
        <label className="field" style={{ flex: '1 1 90px' }}>
          <span className="muted">Weight (lb)</span>
          <input type="number" step="0.1" min="0" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </label>
        {isMagical && (
          <label className="field-inline" style={{ flex: '0 0 auto' }}>
            <input type="checkbox" checked={attunes} onChange={(e) => setAttunes(e.target.checked)} />
            <span className="muted">Requires attunement</span>
          </label>
        )}
      </div>
      <label className="field" style={{ marginTop: 8 }}>
        <span className="muted">Properties / notes (optional)</span>
        <textarea rows={2} value={properties} onChange={(e) => setProperties(e.target.value)}
          placeholder="Damage dice, bonuses, special abilities…" />
      </label>
      <div style={{ marginTop: 10 }}>
        <button type="submit" disabled={!name.trim() || create.isPending}>
          {create.isPending ? 'Adding…' : 'Add definition'}
        </button>
        {create.isError && (
          <span className="muted" style={{ marginLeft: 8, color: 'var(--color-danger, #e53e3e)' }}>
            {errorText(create.error)}
          </span>
        )}
      </div>
    </form>
  )
}

// ── Catalog: edit definition ─────────────────────────────────────────────────

function EditEquipmentDialog({
  campaignId, equipment, onClose,
}: { campaignId: string; equipment: Equipment; onClose: () => void }) {
  const update = useUpdateEquipment(campaignId)
  const [rarity, setRarity] = useState(equipment.rarity ?? '')
  const [attunes, setAttunes] = useState(equipment.requires_attunement)
  const [valueGp, setValueGp] = useState(equipment.value_gp ?? '')
  const [weight, setWeight] = useState(equipment.weight_lb?.toString() ?? '')
  const [properties, setProperties] = useState(equipment.properties ?? '')
  const [attNotes, setAttNotes] = useState(equipment.attunement_notes ?? '')
  const isMagical = equipment.item_type === 'magical'

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    update.mutate(
      {
        equipId: equipment.entity_id,
        rarity: isMagical ? rarity || null : null,
        requires_attunement: isMagical ? attunes : false,
        value_gp: valueGp.trim() || null,
        weight_lb: weight.trim() ? Number(weight) : null,
        properties: properties.trim() || null,
        attunement_notes: attNotes.trim() || null,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal title={`Edit — ${equipment.name}`} onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {isMagical && (
          <>
            <label className="field">
              <span className="muted">Rarity</span>
              <select value={rarity} onChange={(e) => setRarity(e.target.value)}>
                <option value="">— none —</option>
                {RARITIES.map((r) => <option key={r} value={r}>{rarityLabel(r)}</option>)}
              </select>
            </label>
            <label className="field-inline">
              <input type="checkbox" checked={attunes} onChange={(e) => setAttunes(e.target.checked)} />
              <span className="muted">Requires attunement</span>
            </label>
            <label className="field">
              <span className="muted">Attunement notes</span>
              <textarea rows={2} value={attNotes} onChange={(e) => setAttNotes(e.target.value)} />
            </label>
          </>
        )}
        <div className="row" style={{ gap: 8 }}>
          <label className="field" style={{ flex: 1 }}>
            <span className="muted">Value</span>
            <input value={valueGp} onChange={(e) => setValueGp(e.target.value)} placeholder="e.g. 15 gp" />
          </label>
          <label className="field" style={{ flex: 1 }}>
            <span className="muted">Weight (lb)</span>
            <input type="number" step="0.1" min="0" value={weight} onChange={(e) => setWeight(e.target.value)} />
          </label>
        </div>
        <label className="field">
          <span className="muted">Properties / notes</span>
          <textarea rows={3} value={properties} onChange={(e) => setProperties(e.target.value)} />
        </label>
        <div className="row" style={{ gap: 8 }}>
          <button type="submit" disabled={update.isPending}>
            {update.isPending ? 'Saving…' : 'Save'}
          </button>
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        </div>
        {update.isError && (
          <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)', margin: 0 }}>{errorText(update.error)}</p>
        )}
      </form>
    </Modal>
  )
}

// ── Catalog: definition row ──────────────────────────────────────────────────

function EquipmentRow({
  equipment, campaignId, onAddCopy,
}: { equipment: Equipment; campaignId: string; onAddCopy: (e: Equipment) => void }) {
  const [editOpen, setEditOpen] = useState(false)
  const del = useDeleteEquipment(campaignId)
  const saveToLib = useSaveToLibrary(campaignId)
  const rarityColor = equipment.rarity ? RARITY_COLORS[equipment.rarity] : undefined

  return (
    <>
      <li style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
        borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap',
      }}>
        {equipment.item_type === 'magical' && <span title="Magical" style={{ fontSize: 16 }}>✨</span>}
        <Link className="linkish" to="/entities/$entityId" params={{ entityId: equipment.entity_id }}
          style={{ fontWeight: 600, flex: '1 1 180px', minWidth: 0 }}>
          {equipment.name}
        </Link>
        {equipment.rarity && (
          <span className="badge" style={{ color: rarityColor, borderColor: rarityColor, fontSize: 11 }}>
            {rarityLabel(equipment.rarity)}
          </span>
        )}
        {equipment.requires_attunement && (
          <span className="badge" title="Requires attunement" style={{ fontSize: 11 }}>🔮 attune</span>
        )}
        {equipment.value_gp && <span className="muted" style={{ fontSize: 12 }}>⚖ {equipment.value_gp}</span>}
        <span className="badge" style={{ fontSize: 12 }} title="Number of copies in the world">
          {equipment.instance_count} {equipment.instance_count === 1 ? 'copy' : 'copies'}
        </span>
        <span className="row" style={{ gap: 4, flex: '0 0 auto' }}>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => onAddCopy(equipment)}>
            + Copy
          </button>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setEditOpen(true)}>
            Edit
          </button>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} disabled={saveToLib.isPending}
            title="Save this definition to the shared library as a reusable template"
            onClick={() => saveToLib.mutate(equipment.entity_id)}>
            {saveToLib.isSuccess ? '✓ Library' : '→ Library'}
          </button>
          <button className="ghost tag-x" title="Delete definition"
            onClick={() => {
              if (confirm(`Delete "${equipment.name}" and all ${equipment.instance_count} copies?`)) {
                del.mutate(equipment.entity_id)
              }
            }}>×</button>
        </span>
      </li>
      {editOpen && (
        <EditEquipmentDialog campaignId={campaignId} equipment={equipment} onClose={() => setEditOpen(false)} />
      )}
    </>
  )
}

// ── Items: add a copy of a definition ────────────────────────────────────────

function AddCopyDialog({
  campaignId, definitions, preselect, onClose,
}: {
  campaignId: string
  definitions: Equipment[]
  preselect?: Equipment | null
  onClose: () => void
}) {
  const create = useCreateItem(campaignId)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: pcs } = useEntities(campaignId, { entity_type: 'pc' })
  const [equipmentId, setEquipmentId] = useState(preselect?.entity_id ?? definitions[0]?.entity_id ?? '')
  const [label, setLabel] = useState('')
  const [holderType, setHolderType] = useState('unowned')
  const [holderId, setHolderId] = useState('')
  const [locationId, setLocationId] = useState('')

  const needsId = holderType === 'npc' || holderType === 'pc' || holderType === 'location'
  const holderEntities = holderType === 'npc' ? npcs : holderType === 'pc' ? pcs : holderType === 'location' ? locations : []

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!equipmentId) return
    create.mutate(
      {
        equipment_id: equipmentId,
        instance_label: label.trim() || null,
        initial_holder_type: holderType,
        initial_holder_id: needsId ? holderId || null : null,
        initial_location_id: holderType === 'location' ? null : locationId || null,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal title="Add a copy" onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label className="field">
          <span className="muted">Definition</span>
          <select value={equipmentId} onChange={(e) => setEquipmentId(e.target.value)}>
            {definitions.map((d) => <option key={d.entity_id} value={d.entity_id}>{d.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span className="muted">Label (optional — distinguishes this copy)</span>
          <input placeholder="e.g. “the rusty one”" value={label} onChange={(e) => setLabel(e.target.value)} />
        </label>
        <label className="field">
          <span className="muted">Initial holder</span>
          <select value={holderType} onChange={(e) => { setHolderType(e.target.value); setHolderId('') }}>
            {HOLDER_TYPES.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
        {needsId && (
          <label className="field">
            <span className="muted">Select {holderType}</span>
            <select value={holderId} onChange={(e) => setHolderId(e.target.value)}>
              <option value="">— choose —</option>
              {holderEntities?.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
            </select>
          </label>
        )}
        {holderType !== 'location' && (
          <label className="field">
            <span className="muted">Physical location (optional)</span>
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
              <option value="">— none —</option>
              {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
        )}
        <div className="row" style={{ gap: 8 }}>
          <button type="submit" disabled={!equipmentId || create.isPending || (needsId && !holderId)}>
            {create.isPending ? 'Adding…' : 'Add copy'}
          </button>
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        </div>
        {create.isError && (
          <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)', margin: 0 }}>{errorText(create.error)}</p>
        )}
      </form>
    </Modal>
  )
}

// ── Items: transfer ──────────────────────────────────────────────────────────

function TransferDialog({
  campaignId, item, onClose,
}: { campaignId: string; item: Item; onClose: () => void }) {
  const transfer = useTransferItem(campaignId)
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: pcs } = useEntities(campaignId, { entity_type: 'pc' })
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })

  const [holderType, setHolderType] = useState(item.current_holder_type ?? 'unowned')
  const [holderId, setHolderId] = useState(item.current_holder_id ?? '')
  const [locationId, setLocationId] = useState(item.current_location_id ?? '')
  const [reason, setReason] = useState('')

  const holderEntities = holderType === 'npc' ? npcs : holderType === 'pc' ? pcs : holderType === 'location' ? locations : []
  const needsId = holderType === 'npc' || holderType === 'pc' || holderType === 'location'

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    transfer.mutate(
      {
        itemId: item.item_id,
        holder_type: holderType || 'unowned',
        holder_id: needsId ? holderId || null : null,
        location_id: holderType === 'location' ? null : locationId || null,
        reason: reason.trim() || null,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal title={`Transfer — ${item.equipment_name}`} onClose={onClose}>
      <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <label className="field">
          <span className="muted">New holder</span>
          <select value={holderType} onChange={(e) => { setHolderType(e.target.value); setHolderId('') }}>
            {HOLDER_TYPES.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
        {needsId && (
          <label className="field">
            <span className="muted">Select {holderType}</span>
            <select value={holderId} onChange={(e) => setHolderId(e.target.value)}>
              <option value="">— choose —</option>
              {holderEntities?.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
            </select>
          </label>
        )}
        {holderType !== 'location' && (
          <label className="field">
            <span className="muted">Physical location (optional)</span>
            <select value={locationId} onChange={(e) => setLocationId(e.target.value)}>
              <option value="">— none —</option>
              {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </label>
        )}
        <label className="field">
          <span className="muted">Reason (optional)</span>
          <input placeholder="e.g. sold, looted, gifted…" value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <div className="row" style={{ gap: 8 }}>
          <button type="submit" disabled={transfer.isPending || (needsId && !holderId)}>
            {transfer.isPending ? 'Transferring…' : 'Transfer'}
          </button>
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
        </div>
        {transfer.isError && (
          <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)', margin: 0 }}>{errorText(transfer.error)}</p>
        )}
      </form>
    </Modal>
  )
}

// ── Items: ownership history ─────────────────────────────────────────────────

function HistoryPanel({
  campaignId, item, onClose,
}: { campaignId: string; item: Item; onClose: () => void }) {
  const { data: history, isLoading, isError, error } = useItemHistory(campaignId, item.item_id)

  return (
    <Modal title={`Ownership history — ${item.equipment_name}`} onClose={onClose} width={560}>
      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>{errorText(error)}</p>}
      {!isLoading && !history?.length && <p className="muted">No ownership history yet.</p>}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {history?.map((row, i) => (
          <li key={`${row.from_game}-${i}`} style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap' }}>
            <span className="mono" style={{ fontSize: 12, color: 'var(--color-muted)' }}>{row.from_label}</span>
            <span style={{ color: 'var(--color-muted)' }}>→</span>
            <span className="mono" style={{ fontSize: 12, color: 'var(--color-muted)' }}>{row.to_label ?? 'now'}</span>
            <strong>{row.holder_name ?? row.holder_type ?? 'Unowned'}</strong>
            {row.location_name && <span className="badge">📍 {row.location_name}</span>}
          </li>
        ))}
      </ul>
    </Modal>
  )
}

// ── Items: instance row ──────────────────────────────────────────────────────

function ItemRow({ item, campaignId }: { item: Item; campaignId: string }) {
  const [transferOpen, setTransferOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const del = useDeleteItem(campaignId)
  const rarityColor = item.rarity ? RARITY_COLORS[item.rarity] : undefined
  const displayName = item.instance_label
    ? `${item.equipment_name} · ${item.instance_label}`
    : item.equipment_name

  return (
    <>
      <li style={{
        display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
        borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap',
      }}>
        {item.item_type === 'magical' && <span title="Magical" style={{ fontSize: 16 }}>✨</span>}
        <Link className="linkish" to="/entities/$entityId" params={{ entityId: item.equipment_id }}
          style={{ fontWeight: 600, flex: '1 1 180px', minWidth: 0 }}>
          {displayName}
        </Link>
        {item.rarity && (
          <span className="badge" style={{ color: rarityColor, borderColor: rarityColor, fontSize: 11 }}>
            {rarityLabel(item.rarity)}
          </span>
        )}
        {item.requires_attunement && (
          <span className="badge" title="Requires attunement" style={{ fontSize: 11 }}>🔮 attune</span>
        )}
        {item.value_gp && <span className="muted" style={{ fontSize: 12 }}>⚖ {item.value_gp}</span>}
        <span className="badge" style={{ fontSize: 12 }}>{holderLabel(item)}</span>
        {item.current_location_name && (
          <span className="badge" style={{ fontSize: 12 }}>📍 {item.current_location_name}</span>
        )}
        <span className="row" style={{ gap: 4, flex: '0 0 auto' }}>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setTransferOpen(true)}>Transfer</button>
          <button className="ghost" style={{ fontSize: 12, padding: '2px 8px' }} onClick={() => setHistoryOpen(true)}>History</button>
          <button className="ghost tag-x" title="Delete copy"
            onClick={() => { if (confirm(`Delete this copy of "${item.equipment_name}"?`)) del.mutate(item.item_id) }}>×</button>
        </span>
      </li>
      {transferOpen && <TransferDialog campaignId={campaignId} item={item} onClose={() => setTransferOpen(false)} />}
      {historyOpen && <HistoryPanel campaignId={campaignId} item={item} onClose={() => setHistoryOpen(false)} />}
    </>
  )
}

// ── Items: filter bar ────────────────────────────────────────────────────────

function ItemFilterBar({
  filters, setFilters, campaignId,
}: { filters: ItemFilters; setFilters: (f: ItemFilters) => void; campaignId: string }) {
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: pcs } = useEntities(campaignId, { entity_type: 'pc' })
  const active = Object.values(filters).some((v) => v !== undefined && v !== '')
  const setF = (patch: ItemFilters) => setFilters({ ...filters, ...patch })

  const holderEntities =
    filters.holder_type === 'npc' ? npcs :
    filters.holder_type === 'pc' ? pcs :
    filters.holder_type === 'location' ? locations : undefined

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label className="field-inline">
          <span className="muted">Held by</span>
          <select value={filters.holder_type ?? ''}
            onChange={(e) => setF({ holder_type: e.target.value || undefined, holder_id: undefined })}>
            <option value="">anyone</option>
            {HOLDER_TYPES.map((h) => <option key={h} value={h}>{h}</option>)}
          </select>
        </label>
        {holderEntities && (
          <label className="field-inline">
            <span className="muted">Specific {filters.holder_type}</span>
            <select value={filters.holder_id ?? ''} onChange={(e) => setF({ holder_id: e.target.value || undefined })}>
              <option value="">any</option>
              {holderEntities.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
            </select>
          </label>
        )}
        <label className="field-inline">
          <span className="muted">At location</span>
          <select value={filters.location_id ?? ''} onChange={(e) => setF({ location_id: e.target.value || undefined })}>
            <option value="">anywhere</option>
            {locations?.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        </label>
        {active && <button className="ghost" onClick={() => setFilters({})}>Clear</button>}
      </div>
    </div>
  )
}

// ── Items tab ────────────────────────────────────────────────────────────────

function ItemsTab({ campaignId }: { campaignId: string }) {
  const [filters, setFilters] = useState<ItemFilters>({})
  const { data: items, isLoading, isError, error } = useItems(campaignId, filters)
  const { data: definitions } = useEquipmentList(campaignId)
  const [addOpen, setAddOpen] = useState(false)

  const magical = items?.filter((i) => i.item_type === 'magical') ?? []
  const mundane = items?.filter((i) => i.item_type === 'mundane') ?? []
  const hasDefinitions = (definitions?.length ?? 0) > 0

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <p className="muted" style={{ margin: 0 }}>Physical copies in the world.</p>
        <button disabled={!hasDefinitions} title={hasDefinitions ? '' : 'Create a definition in the Catalog tab first'}
          onClick={() => setAddOpen(true)}>+ Add copy</button>
      </div>

      <ItemFilterBar filters={filters} setFilters={setFilters} campaignId={campaignId} />

      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>Couldn’t load items: {errorText(error)}</p>}
      {!isLoading && !isError && items?.length === 0 && (
        <p className="muted">
          {hasDefinitions ? 'No copies match the current filters.' : 'No equipment yet — add a definition in the Catalog tab, then create copies here.'}
        </p>
      )}

      {magical.length > 0 && (
        <section style={{ marginBottom: 24 }}>
          <h3 style={{ marginBottom: 4 }}>✨ Magical ({magical.length})</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {magical.map((item) => <ItemRow key={item.item_id} item={item} campaignId={campaignId} />)}
          </ul>
        </section>
      )}
      {mundane.length > 0 && (
        <section>
          <h3 style={{ marginBottom: 4 }}>🗡 Mundane ({mundane.length})</h3>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {mundane.map((item) => <ItemRow key={item.item_id} item={item} campaignId={campaignId} />)}
          </ul>
        </section>
      )}

      {addOpen && definitions && (
        <AddCopyDialog campaignId={campaignId} definitions={definitions} onClose={() => setAddOpen(false)} />
      )}
    </>
  )
}

// ── Catalog tab ──────────────────────────────────────────────────────────────

function CatalogTab({ campaignId }: { campaignId: string }) {
  const { data: definitions, isLoading, isError, error } = useEquipmentList(campaignId)
  const [addCopyFor, setAddCopyFor] = useState<Equipment | null>(null)

  return (
    <>
      <CreateEquipmentForm campaignId={campaignId} />
      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>Couldn’t load catalog: {errorText(error)}</p>}
      {!isLoading && !isError && definitions?.length === 0 && (
        <p className="muted">No definitions yet. Add one above to start tracking copies.</p>
      )}
      {definitions && definitions.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {definitions.map((eq) => (
            <EquipmentRow key={eq.entity_id} equipment={eq} campaignId={campaignId} onAddCopy={setAddCopyFor} />
          ))}
        </ul>
      )}
      {addCopyFor && definitions && (
        <AddCopyDialog campaignId={campaignId} definitions={definitions} preselect={addCopyFor}
          onClose={() => setAddCopyFor(null)} />
      )}
    </>
  )
}

// ── Library: create a custom template ────────────────────────────────────────

function CreateLibraryEntryForm() {
  const create = useCreateLibraryEntry()
  const [name, setName] = useState('')
  const [type, setType] = useState('mundane')
  const [rarity, setRarity] = useState('')
  const [attunes, setAttunes] = useState(false)
  const [valueGp, setValueGp] = useState('')
  const [weight, setWeight] = useState('')
  const [properties, setProperties] = useState('')
  const isMagical = type === 'magical'

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(
      {
        name: name.trim(), item_type: type,
        rarity: isMagical ? rarity || null : null,
        requires_attunement: isMagical ? attunes : false,
        value_gp: valueGp.trim() || null,
        weight_lb: weight.trim() ? Number(weight) : null,
        properties: properties.trim() || null,
      },
      { onSuccess: () => { setName(''); setRarity(''); setAttunes(false); setValueGp(''); setWeight(''); setProperties('') } },
    )
  }

  return (
    <form className="card" onSubmit={submit} style={{ marginBottom: 16 }}>
      <h4 style={{ marginTop: 0 }}>Add to library</h4>
      <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
        <label className="field" style={{ flex: '2 1 200px' }}>
          <span className="muted">Name</span>
          <input placeholder="Template name…" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field" style={{ flex: '1 1 110px' }}>
          <span className="muted">Type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {ITEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        {isMagical && (
          <label className="field" style={{ flex: '1 1 130px' }}>
            <span className="muted">Rarity</span>
            <select value={rarity} onChange={(e) => setRarity(e.target.value)}>
              <option value="">— none —</option>
              {RARITIES.map((r) => <option key={r} value={r}>{rarityLabel(r)}</option>)}
            </select>
          </label>
        )}
        <label className="field" style={{ flex: '1 1 100px' }}>
          <span className="muted">Value</span>
          <input placeholder="e.g. 15 gp" value={valueGp} onChange={(e) => setValueGp(e.target.value)} />
        </label>
        <label className="field" style={{ flex: '1 1 90px' }}>
          <span className="muted">Weight (lb)</span>
          <input type="number" step="0.1" min="0" value={weight} onChange={(e) => setWeight(e.target.value)} />
        </label>
        {isMagical && (
          <label className="field-inline" style={{ flex: '0 0 auto' }}>
            <input type="checkbox" checked={attunes} onChange={(e) => setAttunes(e.target.checked)} />
            <span className="muted">Requires attunement</span>
          </label>
        )}
      </div>
      <label className="field" style={{ marginTop: 8 }}>
        <span className="muted">Properties / notes (optional)</span>
        <textarea rows={2} value={properties} onChange={(e) => setProperties(e.target.value)} />
      </label>
      <div style={{ marginTop: 10 }}>
        <button type="submit" disabled={!name.trim() || create.isPending}>
          {create.isPending ? 'Adding…' : 'Add to library'}
        </button>
        {create.isError && (
          <span className="muted" style={{ marginLeft: 8, color: 'var(--color-danger, #e53e3e)' }}>{errorText(create.error)}</span>
        )}
      </div>
    </form>
  )
}

// ── Library: one template row ────────────────────────────────────────────────

function LibraryRow({
  entry, campaignId, imported, onImport, importing,
}: {
  entry: LibraryEntry
  campaignId: string
  imported: boolean
  onImport: (id: string) => void
  importing: boolean
}) {
  const del = useDeleteLibraryEntry()
  const rarityColor = entry.rarity ? RARITY_COLORS[entry.rarity] : undefined

  return (
    <li style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
      borderBottom: '1px solid var(--color-border)', flexWrap: 'wrap',
    }}>
      {entry.item_type === 'magical' && <span title="Magical" style={{ fontSize: 16 }}>✨</span>}
      <span style={{ fontWeight: 600, flex: '1 1 180px', minWidth: 0 }}>{entry.name}</span>
      {entry.rarity && (
        <span className="badge" style={{ color: rarityColor, borderColor: rarityColor, fontSize: 11 }}>
          {rarityLabel(entry.rarity)}
        </span>
      )}
      {entry.requires_attunement && (
        <span className="badge" title="Requires attunement" style={{ fontSize: 11 }}>🔮 attune</span>
      )}
      {entry.value_gp && <span className="muted" style={{ fontSize: 12 }}>⚖ {entry.value_gp}</span>}
      <span className="badge" style={{ fontSize: 11 }} title="Where this template came from">{entry.source}</span>
      <span className="row" style={{ gap: 4, flex: '0 0 auto' }}>
        {imported ? (
          <span className="badge" style={{ fontSize: 12 }} title="Already in this campaign">✓ imported</span>
        ) : (
          <button style={{ fontSize: 12, padding: '2px 10px' }} disabled={!campaignId || importing}
            onClick={() => onImport(entry.id)}>
            Import →
          </button>
        )}
        {entry.source !== 'srd' && (
          <button className="ghost tag-x" title="Remove from library"
            onClick={() => { if (confirm(`Remove "${entry.name}" from the library?`)) del.mutate(entry.id) }}>×</button>
        )}
      </span>
    </li>
  )
}

// ── Library tab ──────────────────────────────────────────────────────────────

function LibraryTab({ campaignId }: { campaignId: string }) {
  const [filters, setFilters] = useState<LibraryFilters>({})
  const { data: entries, isLoading, isError, error } = useEquipmentLibrary(filters)
  const { data: definitions } = useEquipmentList(campaignId)
  const importMut = useImportFromLibrary(campaignId)

  // Library ids already present in this campaign, so we can show "imported".
  const importedIds = new Set((definitions ?? []).map((d) => d.library_id).filter(Boolean) as string[])
  const setF = (patch: LibraryFilters) => setFilters({ ...filters, ...patch })
  const active = Object.values(filters).some((v) => v !== undefined && v !== '')

  return (
    <>
      <p className="muted" style={{ marginTop: 0 }}>
        A shared, campaign-independent catalogue. Import a template to add it to this campaign, then create copies.
      </p>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row" style={{ gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label className="field-inline">
            <span className="muted">Search</span>
            <input placeholder="name…" value={filters.q ?? ''} onChange={(e) => setF({ q: e.target.value || undefined })} />
          </label>
          <label className="field-inline">
            <span className="muted">Type</span>
            <select value={filters.item_type ?? ''} onChange={(e) => setF({ item_type: e.target.value || undefined })}>
              <option value="">all</option>
              {ITEM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="field-inline">
            <span className="muted">Rarity</span>
            <select value={filters.rarity ?? ''} onChange={(e) => setF({ rarity: e.target.value || undefined })}>
              <option value="">any</option>
              {RARITIES.map((r) => <option key={r} value={r}>{rarityLabel(r)}</option>)}
            </select>
          </label>
          {active && <button className="ghost" onClick={() => setFilters({})}>Clear</button>}
        </div>
      </div>

      <CreateLibraryEntryForm />

      {isLoading && <p className="muted">Loading…</p>}
      {isError && <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>Couldn’t load library: {errorText(error)}</p>}
      {importMut.isError && (
        <p className="muted" style={{ color: 'var(--color-danger, #e53e3e)' }}>Import failed: {errorText(importMut.error)}</p>
      )}
      {!isLoading && !isError && entries?.length === 0 && <p className="muted">No templates match.</p>}
      {entries && entries.length > 0 && (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {entries.map((entry) => (
            <LibraryRow
              key={entry.id}
              entry={entry}
              campaignId={campaignId}
              imported={importedIds.has(entry.id)}
              importing={importMut.isPending}
              onImport={(id) => importMut.mutate(id)}
            />
          ))}
        </ul>
      )}
    </>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export function EquipmentPage() {
  const { campaign } = useActiveCampaign()
  const [tab, setTab] = useState('items')

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  return (
    <>
      <h2>Equipment</h2>
      <Tabs
        idPrefix="equipment"
        tabs={[
          { id: 'items', label: 'Items' },
          { id: 'catalog', label: 'Catalog' },
          { id: 'library', label: 'Library' },
        ]}
        activeTab={tab}
        onChange={setTab}
      >
        <TabPanel id="items" activeTab={tab} idPrefix="equipment">
          <ItemsTab campaignId={campaign.id} />
        </TabPanel>
        <TabPanel id="catalog" activeTab={tab} idPrefix="equipment">
          <CatalogTab campaignId={campaign.id} />
        </TabPanel>
        <TabPanel id="library" activeTab={tab} idPrefix="equipment">
          <LibraryTab campaignId={campaign.id} />
        </TabPanel>
      </Tabs>
    </>
  )
}
