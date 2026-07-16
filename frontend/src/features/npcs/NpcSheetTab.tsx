import { useState } from 'react'
import { useStatBlocks } from '../../api/hooks'
import { SheetEditorPanel } from '../rules/SheetEditorPanel'
import type { StatBlock } from '../../api/client'

interface NpcSheetTabProps {
  campaignId: string
  systemId: string
}

export function NpcSheetTab({ campaignId, systemId }: NpcSheetTabProps) {
  const { data: blocks } = useStatBlocks(campaignId, 'npc')
  const [selected, setSelected] = useState<StatBlock | null>(null)

  return (
    <div className="sheet-layout">
      <ul className="entities sheet-list">
        {blocks?.map((b) => (
          <li key={b.id} className={selected?.id === b.id ? 'active-row' : ''}>
            <button className="linkish" onClick={() => setSelected(b)}>
              {b.label || '(untitled)'}
            </button>
          </li>
        ))}
        {blocks?.length === 0 && <p className="muted">No NPC sheets yet.</p>}
        <button
          style={{ marginTop: 12, width: '100%' }}
          onClick={() => setSelected(null)}
        >
          + New NPC Sheet
        </button>
      </ul>

      <div style={{ flex: 1 }}>
        <SheetEditorPanel
          key={selected?.id ?? `new-npc`}
          campaignId={campaignId}
          systemId={systemId}
          sheetType="npc"
          existing={selected}
          onSaved={(b) => setSelected(b)}
        />
      </div>
    </div>
  )
}
