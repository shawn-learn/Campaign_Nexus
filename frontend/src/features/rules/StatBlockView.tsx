import { useSheetLayout } from '../../api/hooks'
import { GenericSheetRenderer } from './GenericSheetRenderer'
import type { LayoutSpec } from './GenericSheetRenderer'
import { StatBlock5e } from './StatBlock5e'
import type { Monster, StatBlock } from '../../api/client'

// A read-only view of any stat block (PC, NPC, monster) across rule systems. 5e monsters
// get the bespoke classic card; everything else falls back to the plugin's schema layout,
// mirroring how the Bestiary chooses a renderer. Used by the combat tracker and anywhere a
// combatant's full stats need to be shown at a glance.
export function StatBlockView({
  systemId,
  block,
}: {
  systemId: string | null
  block: StatBlock
}) {
  const is5eMonster = systemId === 'dnd5e' && block.sheet_type === 'monster'
  const { data: layout } = useSheetLayout(is5eMonster ? null : systemId, block.sheet_type)

  if (is5eMonster) {
    // StatBlock5e reads name/doc/derived; the other Monster fields are unused here.
    const monster = {
      name: block.label, doc: block.doc, derived: block.derived,
    } as unknown as Monster
    return <StatBlock5e monster={monster} />
  }

  if (!layout) return <p className="muted">Loading stat block…</p>
  return (
    <div className="statblock-generic">
      <h4 style={{ marginTop: 0 }}>{block.label}</h4>
      {/* Read-only: swallow edits so the panel never mutates a live sheet. */}
      <GenericSheetRenderer
        layout={layout as unknown as LayoutSpec}
        doc={block.doc as Record<string, unknown>}
        onChange={() => {}}
      />
    </div>
  )
}
