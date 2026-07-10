import { useState } from 'react'
import {
  useCancelScheduledEvent,
  useClock,
  useCreateScheduledEvent,
  useScheduledEvents,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'

const SECONDS_PER_DAY = 24 * 60 * 60 // both shipped calendars use 24h days

// Scheduled-events manager (docs/07, §9.6): festivals, deadlines, NPC arrivals. Firing
// happens automatically when the clock passes them (see the clock widget's advance).
export function ScheduledEventsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: clock } = useClock(campaignId)
  const { data: events } = useScheduledEvents(campaignId)
  const create = useCreateScheduledEvent(campaignId ?? '')
  const cancel = useCancelScheduledEvent(campaignId ?? '')

  const [title, setTitle] = useState('')
  const [inDays, setInDays] = useState(7)
  const [actionType, setActionType] = useState('narrate')
  const [text, setText] = useState('')
  const [flagKey, setFlagKey] = useState('')
  const [flagValue, setFlagValue] = useState(true)
  const [recurring, setRecurring] = useState(false)
  const [everyDays, setEveryDays] = useState(7)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!campaignId || !title.trim() || !clock) return
    const fire_at_game = clock.time_game + inDays * SECONDS_PER_DAY
    const action_json =
      actionType === 'narrate'
        ? { text: text.trim() || title.trim() }
        : { key: flagKey.trim(), value: flagValue }
    create.mutate(
      {
        title: title.trim(),
        fire_at_game,
        action_type: actionType,
        action_json,
        recurrence_days: recurring ? everyDays : null,
      },
      { onSuccess: () => { setTitle(''); setText(''); setFlagKey('') } },
    )
  }

  return (
    <>
      <h2>Scheduled Events</h2>
      <p className="muted">
        These fire automatically as you advance the campaign clock. Current date:{' '}
        {clock?.formatted.label}.
      </p>

      <form className="card" onSubmit={submit}>
        <div className="field">
          <span className="muted">Title</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Feast of Lanterns" />
        </div>
        <div className="row" style={{ gap: 16, flexWrap: 'wrap' }}>
          <label className="field" style={{ minWidth: 120 }}>
            <span className="muted">In (days)</span>
            <input type="number" min={0} value={inDays} onChange={(e) => setInDays(+e.target.value)} />
          </label>
          <label className="field" style={{ minWidth: 140 }}>
            <span className="muted">Action</span>
            <select value={actionType} onChange={(e) => setActionType(e.target.value)}>
              <option value="narrate">Narrate</option>
              <option value="set_flag">Set flag</option>
            </select>
          </label>
          <label className="row muted" style={{ gap: 6, alignSelf: 'flex-end' }}>
            <input type="checkbox" checked={recurring} onChange={(e) => setRecurring(e.target.checked)} />
            Repeat every
            <input
              type="number"
              min={1}
              value={everyDays}
              onChange={(e) => setEveryDays(+e.target.value)}
              disabled={!recurring}
              style={{ width: 52 }}
            />
            days
          </label>
        </div>

        {actionType === 'narrate' ? (
          <div className="field">
            <span className="muted">Narration</span>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="What happens…" />
          </div>
        ) : (
          <div className="row" style={{ gap: 12 }}>
            <label className="field">
              <span className="muted">Flag key</span>
              <input value={flagKey} onChange={(e) => setFlagKey(e.target.value)} placeholder="merchant_alive" />
            </label>
            <label className="row muted" style={{ gap: 6, alignSelf: 'flex-end' }}>
              <input type="checkbox" checked={flagValue} onChange={(e) => setFlagValue(e.target.checked)} />
              value = true
            </label>
          </div>
        )}

        <button type="submit" disabled={!title.trim() || create.isPending}>
          Schedule
        </button>
      </form>

      <ul className="entities">
        {events?.map((ev) => (
          <li key={ev.id} className={ev.status !== 'pending' ? 'deleted' : ''}>
            <span>
              <strong>{ev.title}</strong>
              <span className="muted"> — {ev.fire_at_label}</span>
              {ev.recurrence_days ? <span className="tag">every {ev.recurrence_days}d</span> : null}
            </span>
            <span className="row" style={{ gap: 8 }}>
              <span className="badge">{ev.action_type}</span>
              <span className="badge">{ev.status}</span>
              {ev.status === 'pending' && (
                <button className="tag-x" onClick={() => cancel.mutate(ev.id)} aria-label="cancel">
                  ×
                </button>
              )}
            </span>
          </li>
        ))}
        {events?.length === 0 && <p className="muted">No scheduled events yet.</p>}
      </ul>
    </>
  )
}
