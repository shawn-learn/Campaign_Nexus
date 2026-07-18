import { useState } from 'react'
import { useSpellFacets, useSpells } from '../../api/hooks'
import type { Spell } from '../../api/hooks'

const SCHOOLS = [
  'Abjuration', 'Conjuration', 'Divination', 'Enchantment',
  'Evocation', 'Illusion', 'Necromancy', 'Transmutation',
]

// The catalog is global reference content (like the equipment library), imported at
// runtime via scripts/import_5etools.py. Read-only browser with level/school/class filters.
export function SpellsPage() {
  const [q, setQ] = useState('')
  const [level, setLevel] = useState<string>('')
  const [school, setSchool] = useState('')
  const [klass, setKlass] = useState('')
  const [source, setSource] = useState('')
  const [selected, setSelected] = useState<Spell | null>(null)

  const { data: spells } = useSpells({
    ...(q ? { q } : {}),
    ...(level !== '' ? { level: Number(level) } : {}),
    ...(school ? { school } : {}),
    ...(klass ? { class: klass } : {}),
    ...(source ? { source } : {}),
  })

  // Class and source options come from a facets endpoint rather than a second full fetch
  // of the catalog — the list is ~900 rows and only two dropdowns need it.
  const { data: facets } = useSpellFacets()
  const classes = facets?.classes ?? []
  const sources = facets?.sources ?? []

  const levelLabel = (n: number) => (n === 0 ? 'Cantrip' : `Level ${n}`)
  const components = (s: Spell) =>
    [s.component_v && 'V', s.component_s && 'S', s.component_m && 'M'].filter(Boolean).join(', ')

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Spells</h2>
        <span className="muted" style={{ fontSize: 12 }}>{spells?.length ?? 0} shown</span>
      </div>

      <div className="row filters" style={{ gap: 10, flexWrap: 'wrap' }}>
        <input placeholder="Search…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={level} onChange={(e) => setLevel(e.target.value)}>
          <option value="">All levels</option>
          {Array.from({ length: 10 }, (_, n) => (
            <option key={n} value={n}>{levelLabel(n)}</option>
          ))}
        </select>
        <select value={school} onChange={(e) => setSchool(e.target.value)}>
          <option value="">All schools</option>
          {SCHOOLS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        {classes.length > 0 && (
          <select value={klass} onChange={(e) => setKlass(e.target.value)}>
            <option value="">All classes</option>
            {classes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        )}
        {/* Most spell names appear in both PHB and XPHB, and the 2024 rules changed some of
            them, so the catalog keeps both printings — this is how you pick one. */}
        {sources.length > 1 && (
          <select value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">All sources</option>
            {sources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>

      <div className="sheet-layout">
        <ul className="entities sheet-list">
          {spells?.map((s) => (
            <li key={s.id} className={selected?.id === s.id ? 'active-row' : ''}>
              <button className="linkish" onClick={() => setSelected(s)}>{s.name}</button>
              <span className="row" style={{ gap: 6 }}>
                <span className="badge">{levelLabel(s.level)}</span>
                {s.school && <span className="badge">{s.school}</span>}
                {/* Without this, the two printings of a spell are indistinguishable. */}
                {s.source && <span className="tag">{s.source}</span>}
                {s.concentration && <span className="tag">C</span>}
                {s.ritual && <span className="tag">R</span>}
              </span>
            </li>
          ))}
          {spells?.length === 0 && (
            <p className="muted">
              No spells match. Import content with <code>scripts/import_5etools.py --type spells</code>.
            </p>
          )}
        </ul>

        {selected && (
          <div className="card">
            <h3 style={{ marginTop: 0 }}>{selected.name}</h3>
            <p className="muted" style={{ marginTop: 0 }}>
              {levelLabel(selected.level)}
              {selected.school ? ` · ${selected.school}` : ''}
              {selected.ritual ? ' · Ritual' : ''}
              {selected.source ? ` · ${selected.source}` : ''}
            </p>
            <dl className="spell-meta">
              <Row label="Casting Time" value={selected.casting_time} />
              <Row label="Range" value={selected.range_text} />
              <Row
                label="Components"
                value={
                  [components(selected), selected.material ? `(${selected.material})` : '']
                    .filter(Boolean).join(' ') || null
                }
              />
              <Row label="Duration" value={selected.duration} />
              <Row label="Classes" value={selected.classes} />
              <Row label="Saving Throw" value={selected.saving_throw} />
              <Row label="Damage" value={selected.damage_types} />
            </dl>
            {selected.description && (
              <p style={{ whiteSpace: 'pre-wrap' }}>{selected.description}</p>
            )}
            {selected.higher_levels && (
              // The converted text already carries its own "At Higher Levels" heading.
              <p style={{ whiteSpace: 'pre-wrap' }}>{selected.higher_levels}</p>
            )}
          </div>
        )}
      </div>
    </>
  )
}

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null
  return (
    <div className="row" style={{ gap: 8 }}>
      <dt className="muted" style={{ minWidth: 110 }}>{label}</dt>
      <dd style={{ margin: 0 }}>{value}</dd>
    </div>
  )
}
