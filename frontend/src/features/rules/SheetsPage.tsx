import { useEffect, useState } from 'react'
import {
  useCreateStatBlock,
  useRuleSystems,
  useSheetLayout,
  useStatBlocks,
  useUpdateStatBlock,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { GenericSheetRenderer } from './GenericSheetRenderer'
import type { LayoutSpec } from './GenericSheetRenderer'
import type { StatBlock } from '../../api/client'

// Character-sheet workbench (docs/08): create/edit stat blocks for any installed system
// through the generic, layout-driven renderer. 5e ships a bespoke component in Sprint 10.
export function SheetsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: systems } = useRuleSystems()
  const { data: blocks } = useStatBlocks(campaignId)

  const [systemId, setSystemId] = useState('simpletest')
  const [sheetType, setSheetType] = useState('pc')
  const { data: layout } = useSheetLayout(systemId, sheetType)

  const [selected, setSelected] = useState<StatBlock | null>(null)
  const editing = selected

  return (
    <>
      <h2>Character Sheets</h2>

      <div className="row filters" style={{ gap: 12, flexWrap: 'wrap' }}>
        <select value={systemId} onChange={(e) => { setSystemId(e.target.value); setSelected(null) }}>
          {systems?.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        <select
          value={sheetType}
          onChange={(e) => { setSheetType(e.target.value); setSelected(null) }}
        >
          {(systems?.find((s) => s.id === systemId)?.sheet_types ?? []).map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button onClick={() => setSelected(null)}>+ New sheet</button>
      </div>

      <div className="sheet-layout">
        <ul className="entities sheet-list">
          {blocks?.map((b) => (
            <li key={b.id} className={editing?.id === b.id ? 'active-row' : ''}>
              <button className="linkish" onClick={() => setSelected(b)}>
                {b.label || '(untitled)'}
              </button>
              <span className="badge">{b.sheet_type}</span>
            </li>
          ))}
          {blocks?.length === 0 && <p className="muted">No sheets yet.</p>}
        </ul>

        {campaignId && layout && (
          <SheetEditor
            key={editing?.id ?? `new-${systemId}-${sheetType}`}
            campaignId={campaignId}
            systemId={systemId}
            sheetType={sheetType}
            layout={layout as unknown as LayoutSpec}
            existing={editing}
            onSaved={(b) => setSelected(b)}
          />
        )}
      </div>
    </>
  )
}

function SheetEditor({
  campaignId,
  systemId,
  sheetType,
  layout,
  existing,
  onSaved,
}: {
  campaignId: string
  systemId: string
  sheetType: string
  layout: LayoutSpec
  existing: StatBlock | null
  onSaved: (b: StatBlock) => void
}) {
  const create = useCreateStatBlock(campaignId)
  const update = useUpdateStatBlock(campaignId, existing?.id ?? '')
  const [label, setLabel] = useState(existing?.label ?? '')
  const [doc, setDoc] = useState<Record<string, unknown>>(
    (existing?.doc as Record<string, unknown>) ?? {},
  )
  const [error, setError] = useState<string | null>(null)
  const [derived, setDerived] = useState<Record<string, unknown>>(
    (existing?.derived as Record<string, unknown>) ?? {},
  )

  useEffect(() => {
    setLabel(existing?.label ?? '')
    setDoc((existing?.doc as Record<string, unknown>) ?? {})
    setDerived((existing?.derived as Record<string, unknown>) ?? {})
    setError(null)
  }, [existing])

  const save = () => {
    setError(null)
    const onOk = (b: StatBlock) => {
      setDerived((b.derived as Record<string, unknown>) ?? {})
      onSaved(b)
    }
    const onErr = (e: Error) => setError(e.message)
    if (existing) update.mutate({ label, doc }, { onSuccess: onOk, onError: onErr })
    else create.mutate({ rule_system_id: systemId, sheet_type: sheetType, label, doc }, { onSuccess: onOk, onError: onErr })
  }

  return (
    <div className="card sheet-editor">
      <label className="field">
        <span className="muted">Label</span>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Serah Voss" />
      </label>

      <GenericSheetRenderer layout={layout} doc={doc} onChange={setDoc} />

      {error && <p className="error-text">{error}</p>}

      <div className="row" style={{ justifyContent: 'space-between', marginTop: 8 }}>
        <button onClick={save} disabled={create.isPending || update.isPending}>
          {existing ? 'Save' : 'Create'}
        </button>
        {Object.keys(derived).length > 0 && (
          <span className="muted derived">
            {Object.entries(derived).map(([k, v]) => `${k}: ${String(v)}`).join(' · ')}
          </span>
        )}
      </div>
    </div>
  )
}
