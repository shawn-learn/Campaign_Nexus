import type { Monster } from '../../api/client'

// Bespoke classic-styled D&D 5e stat block (docs/08, §10.5 tier 2). Overrides the generic
// renderer for 5e monsters; other systems fall back to the schema-driven view.
const ABILITIES = ['str', 'dex', 'con', 'int', 'wis', 'cha'] as const

function mod(score: number): string {
  const m = Math.floor((score - 10) / 2)
  return m >= 0 ? `+${m}` : `${m}`
}

function crLabel(cr: number): string {
  if (cr === 0.125) return '1/8'
  if (cr === 0.25) return '1/4'
  if (cr === 0.5) return '1/2'
  return String(cr)
}

interface Damage { dice: string; type?: string }
interface Action {
  name: string
  kind?: string
  to_hit?: number
  reach?: string
  target?: string
  damage?: Damage[]
  description?: string
}

/** "+4 to hit, reach 5 ft., one target. Hit: 1d6+2 slashing." — the printed attack line. */
function attackLine(a: Action): string {
  const parts: string[] = []
  if (a.to_hit !== undefined && a.kind !== 'save') {
    const kind = a.kind === 'ranged' ? 'Ranged' : 'Melee'
    parts.push(`${kind} Weapon Attack: ${a.to_hit >= 0 ? '+' : ''}${a.to_hit} to hit`)
  }
  if (a.reach) parts.push(a.reach)
  if (a.target) parts.push(a.target)
  const head = parts.join(', ')
  const hit = (a.damage ?? [])
    .filter((d) => d.dice && d.dice !== '0')
    .map((d) => `${d.dice}${d.type ? ` ${d.type}` : ''}`)
    .join(' plus ')
  return hit ? `${head}. Hit: ${hit} damage.` : `${head}.`
}

export function StatBlock5e({ monster }: { monster: Monster }) {
  const doc = monster.doc as Record<string, unknown>
  const abilities = (doc.abilities as Record<string, number>) ?? {}
  const cr = Number(doc.challenge_rating ?? 0)
  const traits = (doc.traits as { name: string; description: string }[] | undefined) ?? []
  const actions = (doc.actions as Action[] | undefined) ?? []

  return (
    <div className="statblock">
      <div className="sb-name">{monster.name}</div>
      <div className="sb-sub">
        {String(doc.size ?? '')} {String(doc.type ?? '')}
      </div>
      <div className="sb-rule" />

      <div className="sb-line"><b>Armor Class</b> {String(doc.armor_class ?? '—')}</div>
      <div className="sb-line"><b>Hit Points</b> {String(doc.hit_points ?? '—')}</div>
      {doc.speed ? <div className="sb-line"><b>Speed</b> {String(doc.speed)}</div> : null}

      <div className="sb-rule" />
      <div className="sb-abilities">
        {ABILITIES.map((ab) => (
          <div key={ab} className="sb-ability">
            <div className="sb-ability-name">{ab.toUpperCase()}</div>
            <div className="sb-ability-score">
              {abilities[ab] ?? 10} ({mod(abilities[ab] ?? 10)})
            </div>
          </div>
        ))}
      </div>

      <div className="sb-rule" />
      <div className="sb-line">
        <b>Challenge</b> {crLabel(cr)} ({String(doc.xp ?? 0)} XP) ·{' '}
        <b>Prof</b> +{String((monster.derived as Record<string, unknown>).proficiency_bonus ?? '')}
      </div>

      {traits.length > 0 && <div className="sb-rule" />}
      {traits.map((t) => (
        <div key={t.name} className="sb-trait">
          <b><i>{t.name}.</i></b> {t.description}
        </div>
      ))}

      {actions.length > 0 && (
        <>
          <div className="sb-rule" />
          <div className="sb-heading">Actions</div>
          {actions.map((a) => (
            <div key={a.name} className="sb-trait">
              <b><i>{a.name}.</i></b> {attackLine(a)}
              {a.description ? ` ${a.description}` : ''}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
