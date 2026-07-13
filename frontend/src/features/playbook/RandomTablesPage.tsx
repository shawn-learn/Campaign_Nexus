import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  searchEntities,
  useCreateRandomTable,
  useDeleteRandomTable,
  useRandomTables,
  useUpdateRandomTable,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import type { Entity, RandomTable } from '../../api/client'

interface DraftRow {
  min: string
  max: string
  weight: string
  text: string
  target?: { id: string; name: string }
}

interface RowPayload {
  text: string
  target_entity_id: string | null
  min?: number | null
  max?: number | null
  weight?: number
}

const emptyRow = (): DraftRow => ({ min: '', max: '', weight: '', text: '' })

const toDraftRows = (table: RandomTable): DraftRow[] =>
  table.rows.map((r) => ({
    min: r.min != null ? String(r.min) : '',
    max: r.max != null ? String(r.max) : '',
    weight: r.weight != null ? String(r.weight) : '',
    text: r.text ?? '',
    target:
      r.target_entity_id && r.target_name
        ? { id: r.target_entity_id, name: r.target_name }
        : undefined,
  }))

const buildRows = (rows: DraftRow[], weighted: boolean): RowPayload[] =>
  rows
    .filter((r) => r.text.trim() || r.target)
    .map((r) => ({
      text: r.text.trim(),
      target_entity_id: r.target?.id ?? null,
      ...(weighted
        ? { weight: r.weight ? Number(r.weight) : 1 }
        : { min: r.min ? Number(r.min) : null, max: r.max ? Number(r.max) : null }),
    }))

// Random tables (FR-12.x): build a roll table whose rows can link to encounters, NPCs,
// locations, or other tables. Rolling happens on the table's own entity page.
export function RandomTablesPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: tables } = useRandomTables(campaignId)
  const create = useCreateRandomTable(campaignId ?? '')
  const del = useDeleteRandomTable(campaignId ?? '')
  const [createKey, setCreateKey] = useState(0)
  const [editingId, setEditingId] = useState<string | null>(null)

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const remove = (t: RandomTable) => {
    if (window.confirm(`Delete table “${t.name}” and its ${t.row_count} rows? This cannot be undone.`))
      del.mutate(t.id)
  }

  return (
    <>
      <h2>Random Tables</h2>
      <p className="muted" style={{ marginTop: -6 }}>
        Roll tables whose results can link to encounters, NPCs, or other tables. Open a table
        to roll it; use Edit to change its rows.
      </p>

      <TableForm
        key={createKey}
        campaignId={campaignId}
        submitLabel="Create table"
        pending={create.isPending}
        onSubmit={(payload) =>
          create.mutate(payload, { onSuccess: () => setCreateKey((k) => k + 1) })
        }
      />

      <ul className="entities">
        {tables?.map((t) =>
          editingId === t.id ? (
            <li key={t.id} style={{ display: 'block' }}>
              <EditTableRow
                campaignId={campaignId}
                table={t}
                onDone={() => setEditingId(null)}
              />
            </li>
          ) : (
            <li key={t.id}>
              <Link to="/entities/$entityId" params={{ entityId: t.id }}>{t.name}</Link>
              <span className="row" style={{ gap: 6 }}>
                <span className="badge">{t.dice.trim() || 'weighted'}</span>
                <span className="muted">{t.row_count} rows</span>
                <button className="ghost linkish" onClick={() => setEditingId(t.id)}>Edit</button>
                <button
                  className="ghost tag-x"
                  aria-label="delete table"
                  disabled={del.isPending}
                  onClick={() => remove(t)}
                >
                  ×
                </button>
              </span>
            </li>
          ),
        )}
        {tables?.length === 0 && <p className="muted">No tables yet.</p>}
      </ul>
    </>
  )
}

// Edit wrapper: binds the update mutation to a specific table id and prefills the shared form.
function EditTableRow({
  campaignId,
  table,
  onDone,
}: {
  campaignId: string
  table: RandomTable
  onDone: () => void
}) {
  const update = useUpdateRandomTable(campaignId, table.id)
  return (
    <TableForm
      campaignId={campaignId}
      initialName={table.name}
      initialDice={table.dice}
      initialRows={toDraftRows(table)}
      submitLabel="Save changes"
      pending={update.isPending}
      onCancel={onDone}
      onSubmit={(payload) => update.mutate(payload, { onSuccess: onDone })}
    />
  )
}

// Shared create/edit form: table name, dice mode, and the row editor with per-row link targets.
function TableForm({
  campaignId,
  initialName = '',
  initialDice = '1d20',
  initialRows,
  submitLabel,
  pending,
  onSubmit,
  onCancel,
}: {
  campaignId: string
  initialName?: string
  initialDice?: string
  initialRows?: DraftRow[]
  submitLabel: string
  pending: boolean
  onSubmit: (payload: { name: string; dice: string; rows: RowPayload[] }) => void
  onCancel?: () => void
}) {
  const [name, setName] = useState(initialName)
  const [dice, setDice] = useState(initialDice)
  const [rows, setRows] = useState<DraftRow[]>(initialRows ?? [emptyRow(), emptyRow()])
  const weighted = !dice.trim()

  const setRow = (i: number, patch: Partial<DraftRow>) =>
    setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)))

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onSubmit({ name: name.trim(), dice, rows: buildRows(rows, weighted) })
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <input placeholder="Table name" value={name} onChange={(e) => setName(e.target.value)}
          style={{ flex: 1 }} />
        <label className="row muted" style={{ gap: 4 }}>
          Dice
          <input value={dice} onChange={(e) => setDice(e.target.value)} placeholder="1d20 / d100 / (blank = weighted)"
            style={{ width: 220 }} />
        </label>
      </div>

      <h4 style={{ margin: '12px 0 6px' }}>Rows</h4>
      {rows.map((r, i) => (
        <div key={i} className="row" style={{ gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          {weighted ? (
            <input type="number" min={1} placeholder="wt" value={r.weight} style={{ width: 56 }}
              onChange={(e) => setRow(i, { weight: e.target.value })} />
          ) : (
            <span className="row" style={{ gap: 4 }}>
              <input type="number" placeholder="min" value={r.min} style={{ width: 60 }}
                onChange={(e) => setRow(i, { min: e.target.value })} />
              –
              <input type="number" placeholder="max" value={r.max} style={{ width: 60 }}
                onChange={(e) => setRow(i, { max: e.target.value })} />
            </span>
          )}
          <input placeholder="Result text" value={r.text} style={{ flex: 1, minWidth: 160 }}
            onChange={(e) => setRow(i, { text: e.target.value })} />
          <RowTarget
            campaignId={campaignId}
            target={r.target}
            onPick={(t) => setRow(i, { target: t })}
            onClear={() => setRow(i, { target: undefined })}
          />
          <button type="button" className="tag-x" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button type="button" onClick={() => setRows((rs) => [...rs, emptyRow()])}>+ row</button>

      <div className="row" style={{ gap: 8, marginTop: 12 }}>
        <button type="submit" disabled={!name.trim() || pending}>
          {pending ? 'Saving…' : submitLabel}
        </button>
        {onCancel && (
          <button type="button" className="ghost" onClick={onCancel}>Cancel</button>
        )}
      </div>
    </form>
  )
}

// A compact per-row entity picker: search, pick, or clear a link target.
function RowTarget({
  campaignId,
  target,
  onPick,
  onClear,
}: {
  campaignId: string | null
  target?: { id: string; name: string }
  onPick: (t: { id: string; name: string }) => void
  onClear: () => void
}) {
  const [q, setQ] = useState('')
  const [hits, setHits] = useState<Entity[]>([])

  const search = (value: string) => {
    setQ(value)
    if (!campaignId || !value.trim()) return setHits([])
    void searchEntities(campaignId, value.trim()).then((r) => setHits(r.slice(0, 5)))
  }

  if (target) {
    return (
      <span className="chosen-target">
        → {target.name}
        <button type="button" className="tag-x" onClick={onClear}>×</button>
      </span>
    )
  }
  return (
    <div className="relation-form" style={{ position: 'relative' }}>
      <input placeholder="Link to…" value={q} onChange={(e) => search(e.target.value)} style={{ width: 140 }} />
      {hits.length > 0 && (
        <ul className="picker">
          {hits.map((h) => (
            <li key={h.id}>
              <button type="button" onClick={() => { onPick({ id: h.id, name: h.name }); setQ(''); setHits([]) }}>
                <span>{h.name}</span><span className="mention-type">{h.entity_type}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
