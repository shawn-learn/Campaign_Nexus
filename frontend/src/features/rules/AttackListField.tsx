// The `attack-list` field role: authoring attacks on a monster or a character sheet.
//
// Every rule system that declares this role in its layout gets this editor for free — the
// same bargain `ability-array` makes. The system names its own abilities via `keys`, so
// nothing here knows that 5e has six of them or what they're called.
//
// The one idea worth explaining in the UI: an attack can either state its final numbers (how
// a stat block is printed — the monster doesn't level, so the number is the number) or state
// what it's made of (ability + proficiency + a bare weapon die) and let the rule system add
// it up. The second is what keeps a character's attacks right after they level, which is
// exactly the edit that's easy to forget and hard to notice.

export interface AttackDamage {
  dice: string
  type?: string
  add_ability?: boolean
}
export interface Attack {
  name: string
  kind?: string
  to_hit?: number
  ability?: string
  proficient?: boolean
  bonus?: number
  reach?: string
  target?: string
  damage?: AttackDamage[]
  description?: string
}

const BLANK: Attack = { name: '', kind: 'melee', damage: [{ dice: '' }] }

export function AttackListField({
  label,
  attacks,
  abilityKeys,
  onChange,
}: {
  label: string
  attacks: Attack[]
  /** The system's own ability names; 5e lists six, another system might list four. */
  abilityKeys: string[]
  onChange: (next: Attack[]) => void
}) {
  const patch = (i: number, changes: Partial<Attack>) =>
    onChange(attacks.map((a, n) => (n === i ? { ...a, ...changes } : a)))

  const patchDamage = (i: number, d: number, changes: Partial<AttackDamage>) =>
    patch(i, {
      damage: (attacks[i].damage ?? []).map((x, n) => (n === d ? { ...x, ...changes } : x)),
    })

  return (
    <div className="field">
      <span className="muted">{label}</span>
      {attacks.length === 0 && (
        <p className="muted" style={{ fontSize: 12 }}>
          No attacks yet — nothing to click on this sheet during a fight.
        </p>
      )}

      {attacks.map((attack, i) => {
        // Deriving is opt-in per attack: name an ability and the system does the sum.
        const derived = !!attack.ability
        return (
          <fieldset key={i} className="attack-row">
            <legend className="muted">{attack.name || 'New attack'}</legend>

            <div className="row" style={{ gap: 6 }}>
              <label className="field" style={{ flex: 2 }}>
                <span>Name</span>
                <input
                  value={attack.name ?? ''}
                  onChange={(e) => patch(i, { name: e.target.value })}
                />
              </label>
              <label className="field" style={{ flex: 1 }}>
                <span>Kind</span>
                <select
                  value={attack.kind ?? 'melee'}
                  onChange={(e) => patch(i, { kind: e.target.value })}
                >
                  <option value="melee">Melee</option>
                  <option value="ranged">Ranged</option>
                  <option value="save">Save</option>
                </select>
              </label>
            </div>

            <div className="row" style={{ gap: 6 }}>
              <label className="field" style={{ flex: 1 }}>
                <span>Ability</span>
                <select
                  value={attack.ability ?? ''}
                  onChange={(e) =>
                    patch(i, { ability: e.target.value || undefined })
                  }
                >
                  <option value="">— none (fixed bonus) —</option>
                  {abilityKeys.map((ab) => (
                    <option key={ab} value={ab}>{ab.toUpperCase()}</option>
                  ))}
                </select>
              </label>
              {derived ? (
                <>
                  <label className="field" style={{ flex: 1 }}>
                    <span>Proficient</span>
                    <input
                      type="checkbox"
                      checked={!!attack.proficient}
                      onChange={(e) => patch(i, { proficient: e.target.checked })}
                    />
                  </label>
                  <label className="field" style={{ flex: 1 }}>
                    <span>Magic bonus</span>
                    <input
                      type="number"
                      value={attack.bonus ?? ''}
                      onChange={(e) =>
                        patch(i, { bonus: e.target.value === '' ? undefined : Number(e.target.value) })
                      }
                    />
                  </label>
                </>
              ) : (
                <label className="field" style={{ flex: 1 }}>
                  <span>To hit</span>
                  <input
                    type="number"
                    value={attack.to_hit ?? ''}
                    onChange={(e) =>
                      patch(i, { to_hit: e.target.value === '' ? undefined : Number(e.target.value) })
                    }
                  />
                </label>
              )}
            </div>

            <p className="muted" style={{ fontSize: 11, margin: '2px 0 6px' }}>
              {derived
                ? 'To-hit is worked out from the sheet, so it keeps up when this character levels.'
                : 'A fixed bonus, exactly as printed on a stat block. Pick an ability to have it worked out instead.'}
            </p>

            <div className="row" style={{ gap: 6 }}>
              <label className="field" style={{ flex: 2 }}>
                <span>Reach / range</span>
                <input
                  value={attack.reach ?? ''}
                  placeholder="5 ft."
                  onChange={(e) => patch(i, { reach: e.target.value || undefined })}
                />
              </label>
              <label className="field" style={{ flex: 2 }}>
                <span>Target</span>
                <input
                  value={attack.target ?? ''}
                  placeholder="one target"
                  onChange={(e) => patch(i, { target: e.target.value || undefined })}
                />
              </label>
            </div>

            <span className="muted" style={{ fontSize: 12 }}>Damage</span>
            {(attack.damage ?? []).map((part, d) => (
              <div key={d} className="row" style={{ gap: 6, alignItems: 'flex-end' }}>
                <label className="field" style={{ flex: 1 }}>
                  <span>Dice</span>
                  <input
                    value={part.dice ?? ''}
                    placeholder="1d8"
                    onChange={(e) => patchDamage(i, d, { dice: e.target.value })}
                  />
                </label>
                <label className="field" style={{ flex: 1 }}>
                  <span>Type</span>
                  <input
                    value={part.type ?? ''}
                    placeholder="slashing"
                    onChange={(e) => patchDamage(i, d, { type: e.target.value || undefined })}
                  />
                </label>
                {derived && (
                  <label className="row muted" style={{ gap: 4, marginBottom: 8 }}>
                    <input
                      type="checkbox"
                      checked={!!part.add_ability}
                      title="Add the ability modifier to this roll"
                      onChange={(e) => patchDamage(i, d, { add_ability: e.target.checked || undefined })}
                    />
                    + mod
                  </label>
                )}
                <button
                  className="ghost"
                  style={{ marginBottom: 8 }}
                  aria-label={`Remove damage roll ${d + 1}`}
                  onClick={() =>
                    patch(i, { damage: (attack.damage ?? []).filter((_, n) => n !== d) })
                  }
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="ghost"
              onClick={() => patch(i, { damage: [...(attack.damage ?? []), { dice: '' }] })}
            >
              + damage roll
            </button>

            <label className="field" style={{ marginTop: 6 }}>
              <span>Notes</span>
              <textarea
                rows={2}
                value={attack.description ?? ''}
                onChange={(e) => patch(i, { description: e.target.value || undefined })}
              />
            </label>

            <button
              className="linkish"
              style={{ color: 'var(--danger)' }}
              onClick={() => onChange(attacks.filter((_, n) => n !== i))}
            >
              Remove {attack.name || 'attack'}
            </button>
          </fieldset>
        )
      })}

      <button className="ghost" onClick={() => onChange([...attacks, { ...BLANK }])}>
        + Add attack
      </button>
    </div>
  )
}
