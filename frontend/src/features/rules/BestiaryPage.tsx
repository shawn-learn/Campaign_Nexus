import { useEffect, useMemo, useState } from 'react'
import { useSearch } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import {
  exportBestiary,
  importBestiary,
  useFacetManifest,
  useMakeVariant,
  useMonsters,
  useSheetLayout,
  useStatBlock,
} from '../../api/hooks'
import { downloadJson, exportFilename, pickJsonFile } from '../../lib/jsonFile'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { GenericSheetRenderer } from './GenericSheetRenderer'
import type { LayoutSpec } from './GenericSheetRenderer'
import { SheetEditorPanel } from './SheetEditorPanel'
import { StatBlock5e } from './StatBlock5e'
import type { Monster } from '../../api/client'

// Bestiary browser (FR-11.4): manifest-driven facet filters over the monster table. Every
// label and option comes from the plugin — 5e calls facet1 "CR", Nimble calls it "Level".
export function BestiaryPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const systemId = campaign?.rule_system_id ?? null
  const is5e = systemId === 'dnd5e'
  const { data: facets } = useFacetManifest(systemId)
  const { data: monsterLayout } = useSheetLayout(systemId, 'monster')

  const facetLabel = (key: string, fallback: string) =>
    facets?.find((f) => f.key === key)?.label ?? fallback
  const hasFacet = (key: string) => !!facets?.some((f) => f.key === key)

  const [q, setQ] = useState('')
  // Seed the search from ?q= (the ⌘K palette deep-links a monster here). Re-runs if it changes.
  const { q: qParam } = useSearch({ from: '/bestiary' })
  useEffect(() => { if (qParam) setQ(qParam) }, [qParam])
  const [crMin, setCrMin] = useState<string>('')
  const [crMax, setCrMax] = useState<string>('')
  const [type, setType] = useState('')
  const [editing, setEditing] = useState(false)

  const { data: monsters, refetch: refetchMonsters } = useMonsters(campaignId, {
    ...(q ? { q } : {}),
    ...(crMin ? { facet1_num_gte: Number(crMin) } : {}),
    ...(crMax ? { facet1_num_lte: Number(crMax) } : {}),
    ...(type ? { facet1_text: type } : {}),
  })
  // The kinds on offer are the kinds present, not a hardcoded list of 5e creature types.
  const { data: allMonsters } = useMonsters(campaignId)
  const kinds = useMemo(
    () =>
      [...new Set((allMonsters ?? []).map((m) => m.facets.facet1_text).filter(Boolean))]
        .sort() as string[],
    [allMonsters],
  )

  const makeVariant = useMakeVariant(campaignId ?? '')
  const [selected, setSelected] = useState<Monster | null>(null)
  const fromPack = !!selected?.source.startsWith('content_pack:')
  // The stat block behind the selected monster — what an edit actually writes to.
  const { data: block } = useStatBlock(campaignId, editing ? selected?.stat_block_id ?? null : null)
  const qc = useQueryClient()
  const [ioMsg, setIoMsg] = useState<string | null>(null)

  const doExport = async () => {
    if (!campaignId) return
    const data = await exportBestiary(campaignId)
    downloadJson(exportFilename('bestiary', campaign?.name ?? 'campaign'), data)
  }

  const doImport = async () => {
    if (!campaignId) return
    setIoMsg(null)
    try {
      const payload = await pickJsonFile()
      const result = await importBestiary(campaignId, payload)
      void qc.invalidateQueries({ queryKey: ['monsters', campaignId] })
      setIoMsg(
        `Imported ${result.imported} monster(s)` +
          (result.errors.length ? `; ${result.errors.length} skipped` : ''),
      )
    } catch (e) {
      setIoMsg((e as Error).message)
    }
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Bestiary</h2>
        <div className="row" style={{ gap: 6 }}>
          <button className="ghost" onClick={() => void doExport()}>Export JSON</button>
          <button className="ghost" onClick={() => void doImport()}>Import JSON</button>
        </div>
      </div>
      {ioMsg && <p className="muted">{ioMsg}</p>}

      <div className="row filters" style={{ gap: 10, flexWrap: 'wrap' }}>
        <input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        {hasFacet('facet1_num') && (
          <label className="row muted" style={{ gap: 4 }}>
            {facetLabel('facet1_num', 'Rating')}
            <input type="number" style={{ width: 60 }} value={crMin} onChange={(e) => setCrMin(e.target.value)} placeholder="min" />
            –
            <input type="number" style={{ width: 60 }} value={crMax} onChange={(e) => setCrMax(e.target.value)} placeholder="max" />
          </label>
        )}
        {hasFacet('facet1_text') && (
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All {facetLabel('facet1_text', 'types').toLowerCase()}s</option>
            {kinds.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        )}
      </div>

      <div className="sheet-layout">
        <ul className="entities sheet-list">
          {monsters?.map((m) => (
            <li key={m.id} className={selected?.id === m.id ? 'active-row' : ''}>
              <button className="linkish" onClick={() => setSelected(m)}>{m.name}</button>
              <span className="row" style={{ gap: 6 }}>
                <span className="badge">
                  {facetLabel('facet1_num', 'Rating')} {m.facets.facet1_num ?? '?'}
                </span>
                {m.facets.facet1_text && <span className="badge">{m.facets.facet1_text}</span>}
                {m.variant_of && <span className="tag">variant</span>}
              </span>
            </li>
          ))}
          {monsters?.length === 0 && <p className="muted">No monsters match.</p>}
        </ul>

        {selected && (
          <div>
            {editing && block && systemId && campaignId ? (
              <SheetEditorPanel
                campaignId={campaignId}
                systemId={systemId}
                sheetType="monster"
                existing={block}
                onSaved={() => { setEditing(false); void refetchMonsters() }}
              />
            ) : (
              <>
                {/* A bespoke renderer where one exists; otherwise the plugin's own layout —
                    never a raw JSON dump (docs/08 §10.5). */}
                {is5e ? (
                  <StatBlock5e monster={selected} />
                ) : monsterLayout ? (
                  <div className="card">
                    <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
                    <GenericSheetRenderer
                      layout={monsterLayout as unknown as LayoutSpec}
                      doc={selected.doc as Record<string, unknown>}
                      onChange={() => {}}
                    />
                  </div>
                ) : null}
              </>
            )}

            <div className="row" style={{ gap: 6, marginTop: 10 }}>
              {editing ? (
                <button className="ghost" onClick={() => setEditing(false)}>Done</button>
              ) : fromPack ? (
                // A pack monster is the pack's, not yours: the next content update rewrites
                // it (see bestiary.import_content_packs). Copy-on-write is the way to make
                // it yours — which is what `Make variant` has always been for (FR-11.4).
                <button
                  disabled={makeVariant.isPending}
                  onClick={() =>
                    makeVariant.mutate(selected.id, {
                      onSuccess: (v) => { setSelected(v); setEditing(true) },
                    })
                  }
                >
                  {makeVariant.isPending ? 'Copying…' : 'Make variant to edit'}
                </button>
              ) : (
                <button onClick={() => setEditing(true)}>Edit</button>
              )}
            </div>
            {fromPack && !editing && (
              <p className="muted" style={{ fontSize: 11 }}>
                From the SRD pack — a variant is yours to change, and survives pack updates.
              </p>
            )}
          </div>
        )}
      </div>
    </>
  )
}
