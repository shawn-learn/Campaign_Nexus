import { useEntities } from '../../api/hooks'
import { SearchableSelect } from '../../components/SearchableSelect'
import type { SelectOption } from '../../components/SearchableSelect'
import { CONSEQUENCE_SPECS, SPEC_BY_ACTION, blankConsequence } from './storyModel'
import type { Consequence, ParamKind } from './storyModel'

interface Props {
  campaignId: string
  value: Consequence[]
  onChange: (next: Consequence[]) => void
  disabled?: boolean
}

/**
 * Editor over the closed consequence catalog. Fields are rendered from CONSEQUENCE_SPECS,
 * so the catalog is described in one place and this component never grows a per-action
 * branch. The whole array is emitted on every change — the PATCH replaces wholesale.
 */
export function ConsequenceEditor({ campaignId, value, onChange, disabled }: Props) {
  const { data: quests } = useEntities(campaignId, { entity_type: 'quest' })
  const { data: npcs } = useEntities(campaignId, { entity_type: 'npc' })
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })

  const optionsFor = (kind: ParamKind): SelectOption[] => {
    const src = kind === 'entity:quest' ? quests : kind === 'entity:npc' ? npcs : locations
    return (src ?? []).map((e) => ({ id: e.id, name: e.name }))
  }

  const update = (i: number, patch: Consequence) =>
    onChange(value.map((c, j) => (j === i ? { ...c, ...patch } : c)))

  return (
    <div>
      {value.length === 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          None — activating this beat only records it.
        </p>
      )}

      {value.map((c, i) => {
        const spec = SPEC_BY_ACTION[String(c.action)]
        return (
          <div key={i} className="card" style={{ padding: 8, marginBottom: 8 }}>
            <div className="row" style={{ justifyContent: 'space-between', gap: 6 }}>
              <select
                value={String(c.action ?? '')}
                disabled={disabled}
                // Switching action rebuilds the row so stale params from the previous
                // action cannot ride along and fail backend validation.
                onChange={(e) => update(i, blankConsequence(e.target.value))}
              >
                {CONSEQUENCE_SPECS.map((s) => (
                  <option key={s.action} value={s.action}>{s.label}</option>
                ))}
              </select>
              <button
                className="ghost tag-x"
                disabled={disabled}
                onClick={() => onChange(value.filter((_, j) => j !== i))}
                aria-label="Remove consequence"
              >
                ×
              </button>
            </div>

            {spec?.params.map((p) => (
              <div key={p.key} style={{ marginTop: 6 }}>
                <label className="muted" style={{ fontSize: 12 }}>
                  {p.label}{p.optional ? ' (optional)' : ''}
                </label>
                {p.kind.startsWith('entity:') ? (
                  <SearchableSelect
                    value={String(c[p.key] ?? '')}
                    onChange={(v) => update(i, { [p.key]: v || undefined })}
                    options={optionsFor(p.kind)}
                    disabled={disabled}
                  />
                ) : p.kind === 'flag-value' ? (
                  <FlagValueInput
                    value={c[p.key]}
                    onChange={(v) => update(i, { [p.key]: v })}
                    disabled={disabled}
                  />
                ) : p.kind === 'text' ? (
                  <textarea
                    value={String(c[p.key] ?? '')}
                    disabled={disabled}
                    rows={2}
                    style={{ width: '100%' }}
                    onChange={(e) => update(i, { [p.key]: e.target.value })}
                  />
                ) : (
                  <input
                    value={String(c[p.key] ?? '')}
                    disabled={disabled}
                    style={{ width: '100%' }}
                    onChange={(e) => update(i, { [p.key]: e.target.value })}
                  />
                )}
              </div>
            ))}
          </div>
        )
      })}

      <button
        className="ghost"
        disabled={disabled}
        onClick={() => onChange([...value, blankConsequence('set_flag')])}
      >
        + Add consequence
      </button>
    </div>
  )
}

/**
 * Flags are compared against typed literals by the condition DSL, so a flag written as the
 * string "true" would never satisfy `flag('x') == true`. Make the type explicit.
 */
export function FlagValueInput({
  value,
  onChange,
  disabled,
}: {
  value: unknown
  onChange: (v: unknown) => void
  disabled?: boolean
}) {
  const kind =
    typeof value === 'boolean' ? 'boolean' : typeof value === 'number' ? 'number' : 'string'

  return (
    <div className="row" style={{ gap: 6 }}>
      <select
        value={kind}
        disabled={disabled}
        onChange={(e) => {
          const k = e.target.value
          onChange(k === 'boolean' ? true : k === 'number' ? 0 : '')
        }}
      >
        <option value="boolean">true/false</option>
        <option value="number">number</option>
        <option value="string">text</option>
      </select>
      {kind === 'boolean' ? (
        <select
          value={value ? 'true' : 'false'}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value === 'true')}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      ) : kind === 'number' ? (
        <input
          type="number"
          value={Number(value ?? 0)}
          disabled={disabled}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      ) : (
        <input
          value={String(value ?? '')}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  )
}
