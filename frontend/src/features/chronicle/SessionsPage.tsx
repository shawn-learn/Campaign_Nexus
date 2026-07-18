import { useState } from 'react'
import {
  useCaptureNote,
  useCreateSession,
  useSessionAction,
  useSessionDetail,
  useSessions,
  useDeleteSession,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'

// Session log + live-session controls (FR-9). While a session is live, every domain event
// is stamped to it; the detail view shows those events and the entities they touched.
export function SessionsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: sessions } = useSessions(campaignId)
  const create = useCreateSession(campaignId ?? '')
  const start = useSessionAction(campaignId ?? '', 'start')
  const end = useSessionAction(campaignId ?? '', 'end')
  const deleteSession = useDeleteSession(campaignId ?? '')
  const note = useCaptureNote(campaignId ?? '')

  const live = sessions?.find((s) => s.status === 'live') ?? null
  const [selected, setSelected] = useState<string | null>(null)
  const { data: detail } = useSessionDetail(campaignId, selected)
  const [noteText, setNoteText] = useState('')

  const submitNote = (e: React.FormEvent) => {
    e.preventDefault()
    if (!noteText.trim()) return
    note.mutate(noteText.trim(), { onSuccess: () => setNoteText('') })
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>Sessions</h2>
        <button onClick={() => create.mutate()}>+ New session</button>
      </div>

      {live && (
        <div className="card live-banner">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong>● Session {live.session_number} is live</strong>
            <button className="danger-btn" onClick={() => end.mutate(live.id)}>End session</button>
          </div>
          <form className="row" onSubmit={submitNote} style={{ marginTop: 10 }}>
            <input placeholder="Quick note…" value={noteText} onChange={(e) => setNoteText(e.target.value)} style={{ flex: 1 }} />
            <button type="submit" disabled={note.isPending}>Capture</button>
          </form>
        </div>
      )}

      <ul className="entities">
        {sessions?.map((s) => (
          <li key={s.id}>
            <button className="linkish" onClick={() => setSelected(s.id)}>
              Session {s.session_number}
            </button>
            <span className="row" style={{ gap: 8 }}>
              <span className="badge">{s.status}</span>
              {s.status === 'planned' && !live && (
                <button onClick={() => start.mutate(s.id)}>Start</button>
              )}
              {s.status !== 'live' && (
                <button className="ghost tag-x" title="Delete session" onClick={() => {
                  if (confirm(`Delete Session ${s.session_number}?`)) {
                    deleteSession.mutate(s.id)
                  }
                }}>×</button>
              )}
            </span>
          </li>
        ))}
        {sessions?.length === 0 && <p className="muted">No sessions yet.</p>}
      </ul>

      {detail && (
        <div className="card">
          <h3 style={{ marginTop: 0 }}>Session {detail.session_number}</h3>
          {(detail.entities ?? []).length > 0 && (
            <p className="muted">
              Featuring: {(detail.entities ?? []).map((e) => e.name).join(', ')}
            </p>
          )}
          <ul className="feed">
            {(detail.events ?? []).map((ev, i) => (
              <li key={i}>
                <span className="badge">{ev.event_type}</span>
                <span>{ev.narrative_text}</span>
              </li>
            ))}
            {(detail.events ?? []).length === 0 && <p className="muted">No events recorded.</p>}
          </ul>
        </div>
      )}
    </>
  )
}
