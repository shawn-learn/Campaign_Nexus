import { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  exportBestiary,
  importBestiary,
  useFacetManifest,
  useMakeVariant,
  useMonsters,
  useSheetLayout,
} from '../../api/hooks'
import { downloadJson, exportFilename, pickJsonFile } from '../../lib/jsonFile'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { GenericSheetRenderer } from './GenericSheetRenderer'
import type { LayoutSpec } from './GenericSheetRenderer'
import { StatBlock5e } from './StatBlock5e'
import type { Monster } from '../../api/client'

// Bestiary browser (FR-11.4): manifest-driven facet filters over the monster table. Every
// label and option comes from the plugin — 5e calls facet1 "CR", Nimble calls it "Level".
export function BestiaryPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const systemId = campaign?.rule_system_id ?? null

  // The kinds on offer are the kinds present, not a hardcoded list of 5e creature types.
  const { data: allMonsters } = useMonsters(campaignId)
  const kinds = useMemo(
    () =>
      [...new Set((allMonsters ?? []).map((m) => m.facets.facet1_text).filter(Boolean))]
        .sort() as string[],
    [allMonsters],
  )

  // Facet labels and filters follow the *monsters present*, not the campaign's system: an
  // imported single-system pack (e.g. a Nimble bestiary in a 5e campaign) should be filtered
  // by "Level", not "CR". Only fall back to the campaign system when the list is empty or
  // genuinely mixes systems, where no single manifest is correct.
  const listSystemId = useMemo(() => {
    const systems = new Set((allMonsters ?? []).map((m) => m.rule_system_id))
    return systems.size === 1 ? [...systems][0] : systemId
  }, [allMonsters, systemId])
  const { data: facets } = useFacetManifest(listSystemId)

  const facetLabel = (key: string, fallback: string) =>
    facets?.find((f) => f.key === key)?.label ?? fallback
  const hasFacet = (key: string) => !!facets?.some((f) => f.key === key)

  // The detail pane renders each monster by its *own* rule system, not the campaign's — a
  // bestiary can hold monsters from another system (e.g. an imported Nimble pack in a 5e
  // campaign), and the 5e stat block would show blank fields for a non-5e doc.
  const [selected, setSelected] = useState<Monster | null>(null)
  const detailSystemId = selected?.rule_system_id ?? systemId
  const detailIs5e = detailSystemId === 'dnd5e'
  const { data: monsterLayout } = useSheetLayout(detailSystemId, 'monster')

  const [q, setQ] = useState('')
  const [crMin, setCrMin] = useState<string>('')
  const [crMax, setCrMax] = useState<string>('')
  const [type, setType] = useState('')

  const { data: monsters } = useMonsters(campaignId, {
    ...(q ? { q } : {}),
    ...(crMin ? { facet1_num_gte: Number(crMin) } : {}),
    ...(crMax ? { facet1_num_lte: Number(crMax) } : {}),
    ...(type ? { facet1_text: type } : {}),
  })

  const makeVariant = useMakeVariant(campaignId ?? '')
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
            {/* A bespoke renderer where one exists; otherwise the plugin's own layout —
                never a raw JSON dump (docs/08 §10.5). */}
            {detailIs5e ? (
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
            <button
              style={{ marginTop: 10 }}
              disabled={makeVariant.isPending}
              onClick={() => makeVariant.mutate(selected.id, { onSuccess: (v) => setSelected(v) })}
            >
              Make variant
            </button>
          </div>
        )}
      </div>
    </>
  )
}
