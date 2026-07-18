// Types and formatters for a 5e monster `doc`, shared by the stat-block renderer.
// The doc is schema-validated server-side (`_MONSTER_SCHEMA` in the dnd5e plugin); this
// mirrors the optional half of that shape so the renderer isn't casting `unknown` per field.

export interface Damage {
  dice: string
  type?: string
}

export interface Action {
  name: string
  kind?: string
  to_hit?: number
  reach?: string
  target?: string
  damage?: Damage[]
  description?: string
  cost?: number
}

export interface NamedEntry {
  name?: string
  description?: string
}

export interface DamageGroup {
  types?: string[]
  note?: string
  special?: string
}

export interface Senses {
  darkvision?: number
  blindsight?: number
  truesight?: number
  tremorsense?: number
  blind_beyond?: boolean
  other?: string[]
}

export interface SpellSlots {
  level: number
  slots?: number
  spells?: string[]
}

export interface Spellcasting {
  name?: string
  kind?: 'prepared' | 'known' | 'innate'
  ability?: string
  save_dc?: number
  attack_bonus?: number
  caster_level?: number
  description?: string
  at_will?: string[]
  per_day?: { uses: number; each?: boolean; spells?: string[] }[]
  slots?: SpellSlots[]
}

export interface MonsterDoc {
  size?: string
  type?: string
  alignment?: string
  armor_class?: number
  armor_class_note?: string
  hit_points?: number
  hit_dice?: string
  hit_points_note?: string
  speed?: string
  abilities?: Record<string, number>
  challenge_rating?: number
  xp?: number
  saving_throws?: Record<string, number>
  skills?: Record<string, number>
  senses?: Senses
  languages?: string[]
  telepathy?: number
  damage_resistances?: DamageGroup[]
  damage_immunities?: DamageGroup[]
  damage_vulnerabilities?: DamageGroup[]
  condition_immunities?: string[]
  traits?: NamedEntry[]
  multiattack?: { description?: string; attacks?: { name: string; count?: number }[] }
  actions?: Action[]
  bonus_actions?: Action[]
  reactions?: Action[]
  legendary_actions?: { count?: number; description?: string; options?: Action[] }
  spellcasting?: Spellcasting[]
  lair_actions?: { description?: string; initiative?: number; options?: NamedEntry[] }
  regional_effects?: { description?: string; effects?: NamedEntry[]; fades?: string }
  source?: string
  page?: number
}

export interface MonsterDerived {
  ability_modifiers?: Record<string, number>
  proficiency_bonus?: number
  saving_throws?: Record<string, number>
  skill_modifiers?: Record<string, number>
  passive_perception?: number
  has_lair?: boolean
  lair_initiative?: number | null
}

export const ABILITIES = ['str', 'dex', 'con', 'int', 'wis', 'cha'] as const

export function signed(n: number): string {
  return n >= 0 ? `+${n}` : `${n}`
}

export function abilityMod(score: number): string {
  return signed(Math.floor((score - 10) / 2))
}

export function crLabel(cr: number): string {
  if (cr === 0.125) return '1/8'
  if (cr === 0.25) return '1/4'
  if (cr === 0.5) return '1/2'
  return String(cr)
}

/** "sleight_of_hand" -> "Sleight of Hand" — small words stay lowercase, as printed. */
const MINOR_WORDS = new Set(['of', 'the', 'and'])
export function titleize(key: string): string {
  return key
    .split('_')
    .map((w, i) => (i > 0 && MINOR_WORDS.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(' ')
}

/**
 * The printed line for saves/skills — only the entries the stat block actually states.
 * `derived` holds a complete map (every ability, all 18 skills) so callers never branch on
 * presence, but rendering all of it would show six saves on a creature that prints none.
 */
export function modifierLine(
  printed: Record<string, number> | undefined,
  derived: Record<string, number> | undefined,
): string {
  if (!printed) return ''
  return Object.keys(printed)
    .map((key) => `${titleize(key)} ${signed(derived?.[key] ?? printed[key])}`)
    .join(', ')
}

/** "cold, fire; bludgeoning, piercing and slashing from nonmagical attacks" */
export function damageGroupLine(groups: DamageGroup[] | undefined): string {
  if (!groups?.length) return ''
  return groups
    .map((g) => {
      if (g.special) return g.special
      const types = (g.types ?? []).join(', ')
      return g.note ? `${types} ${g.note}` : types
    })
    .filter(Boolean)
    .join('; ')
}

/** "darkvision 60 ft., blindsight 30 ft. (blind beyond this radius)" */
export function sensesLine(senses: Senses | undefined, passivePerception?: number): string {
  const parts: string[] = []
  for (const kind of ['darkvision', 'blindsight', 'tremorsense', 'truesight'] as const) {
    const range = senses?.[kind]
    if (typeof range === 'number') {
      const suffix = kind === 'blindsight' && senses?.blind_beyond ? ' (blind beyond this radius)' : ''
      parts.push(`${kind} ${range} ft.${suffix}`)
    }
  }
  parts.push(...(senses?.other ?? []))
  if (typeof passivePerception === 'number') parts.push(`passive Perception ${passivePerception}`)
  return parts.join(', ')
}

export function languagesLine(languages?: string[], telepathy?: number): string {
  const parts = [...(languages ?? [])]
  if (typeof telepathy === 'number') parts.push(`telepathy ${telepathy} ft.`)
  return parts.join(', ') || '—'
}

/** The printed lines under a spellcasting block: at-will, N/day each, then slot levels. */
export function spellcastingLines(block: Spellcasting): { label: string; spells: string }[] {
  const lines: { label: string; spells: string }[] = []
  if (block.at_will?.length) lines.push({ label: 'At will', spells: block.at_will.join(', ') })
  for (const entry of block.per_day ?? []) {
    lines.push({
      label: `${entry.uses}/day${entry.each ? ' each' : ''}`,
      spells: (entry.spells ?? []).join(', '),
    })
  }
  for (const slot of block.slots ?? []) {
    const label =
      slot.level === 0
        ? 'Cantrips (at will)'
        : `${ordinal(slot.level)} level (${slot.slots ?? 0} slots)`
    lines.push({ label, spells: (slot.spells ?? []).join(', ') })
  }
  return lines
}

function ordinal(n: number): string {
  if (n === 1) return '1st'
  if (n === 2) return '2nd'
  if (n === 3) return '3rd'
  return `${n}th`
}

/**
 * The full printed body of an action: the derived attack line, or the imported description
 * when that already *is* the printed line.
 *
 * The converter stores both — a structured `to_hit`/`damage` for rolling, and the original
 * sentence in `description`. Rendering both duplicates the text ("Melee Weapon Attack: +9 to
 * hit. Hit: 1d8+4 damage. Melee Weapon Attack +9 to hit, reach 5 ft. …"), so prefer the
 * description whenever it restates the attack, and fall back to the derived line otherwise.
 */
export function actionBody(a: Action): string {
  const line = attackLine(a)
  const description = a.description ?? ''
  if (!description) return line
  if (!line) return description
  // "Melee Weapon Attack" / "Ranged Weapon Attack" in the prose means it is the printed line.
  return /\b(Melee|Ranged)\s+(Weapon|Spell)\s+Attack\b/i.test(description)
    ? description
    : `${line} ${description}`.trim()
}

/** "Melee Weapon Attack: +7 to hit, reach 5 ft. Hit: 2d6+4 slashing plus 2d6 fire damage." */
export function attackLine(a: Action): string {
  const parts: string[] = []
  if (a.to_hit !== undefined && a.kind !== 'save') {
    const kind = a.kind === 'ranged' ? 'Ranged' : 'Melee'
    parts.push(`${kind} Weapon Attack: ${signed(a.to_hit)} to hit`)
  }
  if (a.reach) parts.push(a.reach)
  if (a.target) parts.push(a.target)
  const head = parts.join(', ')
  const hit = (a.damage ?? [])
    .filter((d) => d.dice && d.dice !== '0')
    .map((d) => `${d.dice}${d.type ? ` ${d.type}` : ''}`)
    .join(' plus ')
  if (!head) return hit ? `Hit: ${hit} damage.` : ''
  return hit ? `${head}. Hit: ${hit} damage.` : `${head}.`
}
