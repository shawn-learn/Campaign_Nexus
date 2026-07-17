import { useState } from 'react'
import { useAddCombatant, useMonsters } from '../../api/hooks'
import { Modal } from '../../components/Modal'

// Add a straggler mid-fight: a monster from the bestiary, or something that isn't in it.
//
// The bestiary path sends only the monster's id — HP, the initiative modifier and the die
// all come from the rule system's stat block, server-side, so the browser never has to know
// what a Goblin is. The ad-hoc path is for the thing you invented thirty seconds ago.

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : 'Something went wrong'
}

export function AddCombatantDialog({
  campaignId,
  runId,
  onClose,
}: {
  campaignId: string
  runId: string
  onClose: () => void
}) {
  const [tab, setTab] = useState<'bestiary' | 'adhoc'>('bestiary')
  const [q, setQ] = useState('')
  const [monsterId, setMonsterId] = useState('')
  const [count, setCount] = useState('1')
  const [side, setSide] = useState<'foe' | 'ally'>('foe')
  const [name, setName] = useState('')
  const [maxHp, setMaxHp] = useState('')
  const [initiative, setInitiative] = useState('')

  const { data: monsters, isLoading } = useMonsters(campaignId, q.trim() ? { q: q.trim() } : {})
  const add = useAddCombatant(campaignId, runId)

  const ready = tab === 'bestiary' ? !!monsterId : !!name.trim() && maxHp.trim() !== ''

  const submit = () => {
    if (!ready) return
    const init = initiative.trim() === '' ? null : Number(initiative)
    add.mutate(
      tab === 'bestiary'
        ? { monster_id: monsterId, count: Number(count) || 1, side, initiative: init }
        : { name: name.trim(), max_hp: Number(maxHp), count: Number(count) || 1, side,
            initiative: init },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal title="Add to the fight" onClose={onClose} width={460}>
      <div className="row" style={{ gap: 6, marginBottom: 12 }}>
        <button className={tab === 'bestiary' ? '' : 'ghost'} onClick={() => setTab('bestiary')}>
          From the bestiary
        </button>
        <button className={tab === 'adhoc' ? '' : 'ghost'} onClick={() => setTab('adhoc')}>
          Something else
        </button>
      </div>

      {tab === 'bestiary' ? (
        <>
          <label className="field">
            <span>Search</span>
            <input
              autoFocus
              value={q}
              placeholder="goblin, wolf…"
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Monster</span>
            <select value={monsterId} onChange={(e) => setMonsterId(e.target.value)} size={6}>
              {monsters?.map((m) => (
                <option key={m.id} value={m.id}>{m.name}</option>
              ))}
            </select>
          </label>
          {isLoading && <p className="muted">Loading bestiary…</p>}
          {!isLoading && monsters?.length === 0 && (
            <p className="muted">Nothing matches “{q}”.</p>
          )}
        </>
      ) : (
        <>
          <label className="field">
            <span>Name</span>
            <input
              autoFocus
              value={name}
              placeholder="Swarm of rats"
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Max HP</span>
            <input
              type="number"
              value={maxHp}
              onChange={(e) => setMaxHp(e.target.value)}
            />
          </label>
        </>
      )}

      <div className="row" style={{ gap: 8 }}>
        <label className="field" style={{ flex: 1 }}>
          <span>How many</span>
          <input type="number" min={1} max={20} value={count}
                 onChange={(e) => setCount(e.target.value)} />
        </label>
        <label className="field" style={{ flex: 1 }}>
          <span>Side</span>
          <select value={side} onChange={(e) => setSide(e.target.value as 'foe' | 'ally')}>
            <option value="foe">Foe</option>
            <option value="ally">Ally</option>
          </select>
        </label>
      </div>

      <label className="field">
        <span>Initiative</span>
        <input
          type="number"
          value={initiative}
          placeholder="rolled automatically"
          onChange={(e) => setInitiative(e.target.value)}
        />
      </label>
      <p className="muted" style={{ fontSize: 11, marginTop: -4 }}>
        Leave blank to roll it in. Type a number for something that acts on a player's turn.
      </p>

      {add.isError && (
        <p className="muted" style={{ color: 'var(--danger)' }}>
          Couldn't add: {errorText(add.error)}
        </p>
      )}

      <div className="row" style={{ gap: 6, justifyContent: 'flex-end', marginTop: 12 }}>
        <button className="ghost" onClick={onClose}>Cancel</button>
        <button disabled={!ready || add.isPending} onClick={submit}>
          {add.isPending ? 'Adding…' : 'Add'}
        </button>
      </div>
    </Modal>
  )
}
