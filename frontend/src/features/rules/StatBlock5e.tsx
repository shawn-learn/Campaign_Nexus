import type { Monster } from '../../api/client'
import {
  ABILITIES,
  abilityMod,
  actionBody,
  crLabel,
  damageGroupLine,
  languagesLine,
  modifierLine,
  sensesLine,
  signed,
  spellcastingLines,
  type Action,
  type MonsterDerived,
  type MonsterDoc,
  type NamedEntry,
} from './monsterDoc'

// Bespoke classic-styled D&D 5e stat block (docs/08, §10.5 tier 2). Overrides the generic
// renderer for 5e monsters; other systems fall back to the schema-driven view.

/** One "Label value" line, rendered only when there is a value. */
function Line({ label, value }: { label: string; value: string | number | undefined }) {
  if (value === undefined || value === '' || value === null) return null
  return (
    <div className="sb-line">
      <b>{label}</b> {value}
    </div>
  )
}

/** A named block of prose — traits, lair options, regional effects. */
function Entry({ name, description }: NamedEntry) {
  return (
    <div className="sb-trait">
      {name ? (
        <b>
          <i>{name}.</i>
        </b>
      ) : null}
      {name ? ' ' : ''}
      {description}
    </div>
  )
}

/** An "Actions"-style heading followed by its attacks. Used five times over. */
function ActionSection({ title, actions }: { title: string; actions?: Action[] }) {
  if (!actions?.length) return null
  return (
    <>
      <div className="sb-rule" />
      <div className="sb-heading">{title}</div>
      {actions.map((a) => {
        const cost = a.cost && a.cost > 1 ? ` (Costs ${a.cost} Actions)` : ''
        return (
          <div key={a.name} className="sb-trait">
            <b>
              <i>
                {a.name}
                {cost}.
              </i>
            </b>{' '}
            {actionBody(a)}
          </div>
        )
      })}
    </>
  )
}

export function StatBlock5e({ monster }: { monster: Monster }) {
  const doc = (monster.doc ?? {}) as MonsterDoc
  const derived = (monster.derived ?? {}) as MonsterDerived
  const abilities = doc.abilities ?? {}
  const cr = Number(doc.challenge_rating ?? 0)

  const ac = doc.armor_class_note
    ? `${doc.armor_class ?? '—'} (${doc.armor_class_note})`
    : (doc.armor_class ?? '—')
  const hp = doc.hit_dice ? `${doc.hit_points ?? '—'} (${doc.hit_dice})` : (doc.hit_points ?? '—')
  const subtitle = [doc.size, doc.type].filter(Boolean).join(' ')
  const lair = doc.lair_actions
  const regional = doc.regional_effects

  return (
    <div className="statblock">
      <div className="sb-name">{monster.name}</div>
      <div className="sb-sub">
        {subtitle}
        {doc.alignment ? `, ${doc.alignment}` : ''}
      </div>
      <div className="sb-rule" />

      <Line label="Armor Class" value={ac} />
      <Line label="Hit Points" value={hp} />
      <Line label="Speed" value={doc.speed} />

      <div className="sb-rule" />
      <div className="sb-abilities">
        {ABILITIES.map((ab) => (
          <div key={ab} className="sb-ability">
            <div className="sb-ability-name">{ab.toUpperCase()}</div>
            <div className="sb-ability-score">
              {abilities[ab] ?? 10} ({abilityMod(abilities[ab] ?? 10)})
            </div>
          </div>
        ))}
      </div>

      <div className="sb-rule" />
      {/* Only the saves and skills the block actually prints — `derived` holds a complete
          map, but showing all of it would give every creature six saves and 18 skills. */}
      <Line label="Saving Throws" value={modifierLine(doc.saving_throws, derived.saving_throws)} />
      <Line label="Skills" value={modifierLine(doc.skills, derived.skill_modifiers)} />
      <Line label="Damage Vulnerabilities" value={damageGroupLine(doc.damage_vulnerabilities)} />
      <Line label="Damage Resistances" value={damageGroupLine(doc.damage_resistances)} />
      <Line label="Damage Immunities" value={damageGroupLine(doc.damage_immunities)} />
      <Line label="Condition Immunities" value={(doc.condition_immunities ?? []).join(', ')} />
      <Line label="Senses" value={sensesLine(doc.senses, derived.passive_perception)} />
      <Line label="Languages" value={languagesLine(doc.languages, doc.telepathy)} />
      <div className="sb-line">
        <b>Challenge</b> {crLabel(cr)} ({doc.xp ?? 0} XP) · <b>Prof</b>{' '}
        {signed(derived.proficiency_bonus ?? 0)}
      </div>

      {doc.traits?.length ? <div className="sb-rule" /> : null}
      {(doc.traits ?? []).map((t) => (
        <Entry key={t.name} {...t} />
      ))}

      {doc.spellcasting?.length ? <div className="sb-rule" /> : null}
      {(doc.spellcasting ?? []).map((block) => (
        <div key={block.name ?? 'spellcasting'} className="sb-trait">
          <b>
            <i>{block.name ?? 'Spellcasting'}.</i>
          </b>{' '}
          {block.description}
          {spellcastingLines(block).map((line) => (
            <div key={line.label} className="sb-spell-line">
              <b>{line.label}:</b> {line.spells}
            </div>
          ))}
        </div>
      ))}

      {doc.multiattack || doc.actions?.length ? (
        <>
          <div className="sb-rule" />
          <div className="sb-heading">Actions</div>
          {doc.multiattack ? (
            <Entry name="Multiattack" description={doc.multiattack.description} />
          ) : null}
          {/* A doc upgraded in place can still carry Multiattack inside `actions`; the
              hoisted `multiattack` above is the one to show. */}
          {(doc.actions ?? [])
            .filter((a) => !doc.multiattack || !/^multiattack\b/i.test(a.name))
            .map((a) => (
              <div key={a.name} className="sb-trait">
                <b>
                  <i>{a.name}.</i>
                </b>{' '}
                {actionBody(a)}
              </div>
            ))}
        </>
      ) : null}

      <ActionSection title="Bonus Actions" actions={doc.bonus_actions} />
      <ActionSection title="Reactions" actions={doc.reactions} />
      <ActionSection title="Legendary Actions" actions={doc.legendary_actions?.options} />

      {lair ? (
        <>
          <div className="sb-rule" />
          <div className="sb-heading">Lair Actions</div>
          {lair.description ? <div className="sb-trait">{lair.description}</div> : null}
          {(lair.options ?? []).map((o, i) => (
            <Entry key={o.name || i} {...o} />
          ))}
        </>
      ) : null}

      {regional ? (
        <>
          <div className="sb-rule" />
          <div className="sb-heading">Regional Effects</div>
          {regional.description ? <div className="sb-trait">{regional.description}</div> : null}
          {(regional.effects ?? []).map((e, i) => (
            <Entry key={e.name || i} {...e} />
          ))}
          {regional.fades ? <div className="sb-trait">{regional.fades}</div> : null}
        </>
      ) : null}

      {doc.source ? (
        <div className="sb-source">
          {doc.source}
          {doc.page ? `, p.${doc.page}` : ''}
        </div>
      ) : null}
    </div>
  )
}
