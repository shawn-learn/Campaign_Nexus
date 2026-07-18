import { render, cleanup, within, fireEvent } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AttackListField } from './AttackListField'
import type { Attack } from './AttackListField'

// The `attack-list` field role. The subtlety worth pinning is the fork between an attack
// that states its final numbers (how a stat block prints one) and an attack that states its
// ingredients and lets the rule system add them up (which is what keeps a character's
// attacks right after they level).

afterEach(cleanup)

function renderField(attacks: Attack[]) {
  const onChange = vi.fn()
  const view = render(
    <AttackListField
      label="Attacks"
      attacks={attacks}
      abilityKeys={['str', 'dex']}
      onChange={onChange}
    />,
  )
  return { ui: within(view.container), onChange }
}

describe('AttackListField', () => {
  it('offers a fixed to-hit until an ability is chosen', () => {
    const { ui } = renderField([{ name: 'Scimitar', to_hit: 4, damage: [{ dice: '1d6+2' }] }])

    // No ability named: the number is stated outright, as printed.
    expect(ui.getByLabelText(/to hit/i)).toHaveValue(4)
    expect(ui.queryByLabelText(/proficient/i)).not.toBeInTheDocument()
    expect(ui.getByText(/exactly as printed/i)).toBeInTheDocument()
  })

  it('swaps to derivation once an ability is named', () => {
    const { ui } = renderField([
      { name: 'Longsword', ability: 'str', proficient: true, damage: [{ dice: '1d8' }] },
    ])

    // Derived: no raw bonus to type, but proficiency and a magic plus to declare.
    expect(ui.queryByLabelText(/^to hit$/i)).not.toBeInTheDocument()
    expect(ui.getByLabelText(/proficient/i)).toBeChecked()
    expect(ui.getByLabelText(/magic bonus/i)).toBeInTheDocument()
    expect(ui.getByText(/keeps up when this character levels/i)).toBeInTheDocument()
  })

  it('only offers "+ mod" on damage once the attack derives from an ability', () => {
    const { ui: fixed } = renderField([{ name: 'Bite', to_hit: 4, damage: [{ dice: '1d6+2' }] }])
    // A printed 1d6+2 already contains the modifier; offering to add it again would be a trap.
    expect(fixed.queryByTitle(/add the ability modifier/i)).not.toBeInTheDocument()

    const { ui: derived } = renderField([
      { name: 'Longsword', ability: 'str', damage: [{ dice: '1d8', add_ability: true }] },
    ])
    expect(derived.getByTitle(/add the ability modifier/i)).toBeChecked()
  })

  it('names only the abilities the rule system declares', () => {
    const { ui } = renderField([{ name: 'Jab', ability: 'str', damage: [] }])
    const options = ui.getAllByRole('option').map((o) => o.textContent)
    expect(options).toContain('STR')
    expect(options).toContain('DEX')
    expect(options).not.toContain('CHA') // not in abilityKeys — this system has two
  })

  it('adds and removes attacks', () => {
    const { ui, onChange } = renderField([])
    expect(ui.getByText(/no attacks yet/i)).toBeInTheDocument()

    fireEvent.click(ui.getByRole('button', { name: /add attack/i }))
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ name: '' })])

    const { ui: one, onChange: onChange2 } = renderField([{ name: 'Claw', damage: [] }])
    fireEvent.click(one.getByRole('button', { name: /remove claw/i }))
    expect(onChange2).toHaveBeenCalledWith([])
  })

  it('adds a second damage roll for a rider', () => {
    // A flame tongue is 1d8 slashing + 2d6 fire; the second roll takes no ability modifier.
    const { ui, onChange } = renderField([{ name: 'Blade', damage: [{ dice: '1d8' }] }])
    fireEvent.click(ui.getByRole('button', { name: /\+ damage roll/i }))
    expect(onChange).toHaveBeenCalledWith([
      expect.objectContaining({ damage: [{ dice: '1d8' }, { dice: '' }] }),
    ])
  })
})
