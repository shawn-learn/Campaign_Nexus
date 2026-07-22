// Generic, system-agnostic sheet form driven by a plugin's LayoutSpec (docs/08, §10.5).
// Any rule system gets a working editor with zero frontend work; bespoke per-system
// components (e.g. the 5e stat block in Sprint 10) can override this later.
import { AttackListField } from './AttackListField'
import type { Attack } from './AttackListField'
import { SpellcastingField } from './SpellcastingField'
import type { SpellcastingBlock } from './SpellcastingField'
import { TraitListField } from './TraitListField'
import type { NamedEntry } from './TraitListField'

export interface LayoutField {
  key: string
  label: string
  role: string
  /** For `ability-array`: the sub-keys to render. 5e names six; Nimble names four. */
  keys?: string[]
}
export interface LayoutSection {
  title: string
  fields: LayoutField[]
}
export interface LayoutSpec {
  sections: LayoutSection[]
}

type Doc = Record<string, unknown>

// A field `key` may address a nested path with dots ("legendary_actions.options"), so the
// action-family sub-objects (legendary/lair actions, regional effects, multiattack) are
// editable through the same flat layout. Reading and writing walk the path; writing prunes
// empties so an untouched optional sub-object never materialises as `{}` and fails validation.
function getPath(doc: Doc, key: string): unknown {
  return key.split('.').reduce<unknown>((acc, part) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[part]
    return undefined
  }, doc)
}

function isEmpty(value: unknown): boolean {
  if (value === undefined || value === null || value === '') return true
  if (Array.isArray(value)) return value.length === 0
  if (typeof value === 'object') return Object.keys(value as object).length === 0
  return false
}

function setPath(doc: Doc, key: string, value: unknown): Doc {
  const [head, ...rest] = key.split('.')
  if (rest.length === 0) {
    const next = { ...doc }
    if (isEmpty(value)) delete next[head]
    else next[head] = value
    return next
  }
  const child = (doc[head] && typeof doc[head] === 'object' ? doc[head] : {}) as Doc
  const updatedChild = setPath(child, rest.join('.'), value)
  const next = { ...doc }
  if (isEmpty(updatedChild)) delete next[head]
  else next[head] = updatedChild
  return next
}

interface Props {
  layout: LayoutSpec
  doc: Doc
  onChange: (doc: Doc) => void
}

export function GenericSheetRenderer({ layout, doc, onChange }: Props) {
  const set = (key: string, value: unknown) => onChange(setPath(doc, key, value))

  return (
    <div className="sheet">
      {layout.sections.map((section) => (
        <section key={section.title} className="sheet-section">
          <h4>{section.title}</h4>
          {section.fields.map((field) => (
            <Field key={field.key} field={field} doc={doc} set={set} />
          ))}
        </section>
      ))}
    </div>
  )
}

function Field({ field, doc, set }: { field: LayoutField; doc: Doc; set: (k: string, v: unknown) => void }) {
  const value = getPath(doc, field.key)

  if (field.role === 'paragraph') {
    return (
      <label className="field">
        <span className="muted">{field.label}</span>
        <textarea rows={3} value={(value as string) ?? ''} onChange={(e) => set(field.key, e.target.value)} />
      </label>
    )
  }
  if (field.role === 'number') {
    return (
      <label className="field">
        <span className="muted">{field.label}</span>
        <input
          type="number"
          value={value === undefined || value === null ? '' : (value as number)}
          onChange={(e) => set(field.key, e.target.value === '' ? undefined : Number(e.target.value))}
        />
      </label>
    )
  }
  if (field.role === 'boolean') {
    return (
      <label className="row muted" style={{ gap: 6 }}>
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(field.key, e.target.checked)} />
        {field.label}
      </label>
    )
  }
  if (field.role === 'ability-array') {
    const abilities = (value as Record<string, number>) ?? {}
    // The plugin names its own attributes; fall back to whatever the doc already carries.
    const keys = field.keys ?? Object.keys(abilities)
    return (
      <div className="field">
        <span className="muted">{field.label}</span>
        <div className="ability-grid">
          {keys.map((ab) => (
            <label key={ab} className="ability">
              <span className="ability-name">{ab.toUpperCase()}</span>
              <input
                type="number"
                value={abilities[ab] ?? ''}
                onChange={(e) =>
                  set(field.key, {
                    ...abilities,
                    [ab]: e.target.value === '' ? undefined : Number(e.target.value),
                  })
                }
              />
            </label>
          ))}
        </div>
      </div>
    )
  }
  if (field.role === 'attack-list') {
    return (
      <AttackListField
        label={field.label}
        attacks={(value as Attack[]) ?? []}
        // The plugin names its own abilities, same bargain as `ability-array` above.
        abilityKeys={field.keys ?? []}
        onChange={(next) => set(field.key, next.length ? next : undefined)}
      />
    )
  }
  if (field.role === 'spellcasting') {
    return (
      <SpellcastingField
        label={field.label}
        blocks={(value as SpellcastingBlock[]) ?? []}
        // The plugin names its own abilities, same bargain as `ability-array` above.
        abilityKeys={field.keys ?? []}
        onChange={(next) => set(field.key, next.length ? next : undefined)}
      />
    )
  }
  if (field.role === 'trait-list' || field.role === 'named-entry-list') {
    return (
      <TraitListField
        label={field.label}
        entries={(value as NamedEntry[]) ?? []}
        onChange={(next) => set(field.key, next.length ? next : undefined)}
      />
    )
  }
  // default: text
  return (
    <label className="field">
      <span className="muted">{field.label}</span>
      <input value={(value as string) ?? ''} onChange={(e) => set(field.key, e.target.value)} />
    </label>
  )
}
