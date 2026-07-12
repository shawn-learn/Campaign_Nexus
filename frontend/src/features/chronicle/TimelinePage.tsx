import { useState } from 'react'
import { useClearTimeline, useCreateManualEntry, useSessions, useTimeline } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useCalendar } from '../../lib/useCalendar'

// The campaign timeline (FR-8): a curated projection of significant events + manual lore,
// filterable by session, significance, and hidden state. Dates format locally.
export function TimelinePage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const cal = useCalendar(campaignId)
  const { data: sessions } = useSessions(campaignId)

  const [sessionId, setSessionId] = useState('')
  const [minSig, setMinSig] = useState(0)
  const [includeHidden, setIncludeHidden] = useState(false)

  const { data: entries } = useTimeline(campaignId, {
    ...(sessionId ? { session_id: sessionId } : {}),
    ...(minSig ? { significance_min: minSig } : {}),
    include_hidden: includeHidden,
  })

  const create = useCreateManualEntry(campaignId ?? '')
  const clear = useClearTimeline(campaignId ?? '')
  const [title, setTitle] = useState('')
  const [whenDay, setWhenDay] = useState(0)

  const doClear = () => {
    if (
      window.confirm(
        'Clear the entire timeline (including manual lore) and reset the clock to the campaign start? This cannot be undone.',
      )
    ) {
      clear.mutate()
    }
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim() || !cal) return
    create.mutate(
      { title: title.trim(), occurred_at_game: whenDay * cal.secondsPerDay, significance: 3 },
      { onSuccess: () => setTitle('') },
    )
  }

  const fmt = (minutes: number) => (cal ? cal.format(minutes).label : `${minutes}m`)

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h2>Timeline</h2>
        <button className="danger-btn" disabled={clear.isPending} onClick={doClear}>
          Clear timeline & reset clock
        </button>
      </div>

      <div className="row filters" style={{ gap: 12, flexWrap: 'wrap' }}>
        <select value={sessionId} onChange={(e) => setSessionId(e.target.value)}>
          <option value="">All sessions</option>
          {sessions?.map((s) => (
            <option key={s.id} value={s.id}>
              Session {s.session_number}
            </option>
          ))}
        </select>
        <select value={minSig} onChange={(e) => setMinSig(+e.target.value)}>
          <option value={0}>Any significance</option>
          <option value={2}>Notable+</option>
          <option value={3}>Major+</option>
        </select>
        <label className="row muted" style={{ gap: 6 }}>
          <input type="checkbox" checked={includeHidden} onChange={(e) => setIncludeHidden(e.target.checked)} />
          Show hidden
        </label>
      </div>

      <form className="card row" onSubmit={submit}>
        <input placeholder="Add lore/event…" value={title} onChange={(e) => setTitle(e.target.value)} style={{ flex: 1 }} />
        <label className="row muted" style={{ gap: 4 }}>
          day
          <input type="number" value={whenDay} onChange={(e) => setWhenDay(+e.target.value)} style={{ width: 70 }} />
        </label>
        <button type="submit" disabled={!title.trim() || create.isPending}>Add</button>
      </form>

      <ul className="timeline">
        {entries?.map((e) => (
          <li key={e.id} className={`sig-${e.significance}`}>
            <span className="tl-icon">{e.icon ?? '•'}</span>
            <div>
              <div className="tl-title">{e.title}</div>
              <div className="muted tl-date">
                {fmt(e.occurred_at_game)}
                {e.event_id === null ? ' · lore' : ''}
              </div>
            </div>
          </li>
        ))}
        {entries?.length === 0 && <p className="muted">No timeline entries yet.</p>}
      </ul>
    </>
  )
}
