import { useEffect, useState } from 'react'
import {
  useCreateStatBlock,
  useUpdateStatBlock,
  useSheetLayout,
} from '../../api/hooks'
import { GenericSheetRenderer } from './GenericSheetRenderer'
import type { LayoutSpec } from './GenericSheetRenderer'
import type { StatBlock } from '../../api/client'

interface SheetEditorPanelProps {
  campaignId: string
  systemId: string
  sheetType: string
  existing: StatBlock | null
  onSaved: (b: StatBlock) => void
}

export function SheetEditorPanel({
  campaignId,
  systemId,
  sheetType,
  existing,
  onSaved,
}: SheetEditorPanelProps) {
  const { data: layout } = useSheetLayout(systemId, sheetType)
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

  if (!layout) return <p className="muted">Loading sheet layout…</p>

  return (
    <div className="card sheet-editor">
      <label className="field">
        <span className="muted">Label</span>
        <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="e.g. Character Name" />
      </label>

      <GenericSheetRenderer layout={layout as unknown as LayoutSpec} doc={doc} onChange={setDoc} />

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
