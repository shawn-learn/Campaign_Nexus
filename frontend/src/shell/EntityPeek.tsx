import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useEntity } from '../api/hooks'
import { useUiStore } from '../stores/ui'
import { useRecentsStore } from '../stores/recents'
import { useActiveCampaign } from './useActiveCampaign'

// Entity peek: a side panel that shows a compact view without leaving the current
// screen (docs/12, §12.1 "peek, then commit"). Second action = open the full page.
export function EntityPeek() {
  const peekId = useUiStore((s) => s.peekId)
  const closePeek = useUiStore((s) => s.closePeek)
  const navigate = useNavigate()
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const addRecent = useRecentsStore((s) => s.addRecent)

  const { data: entity } = useEntity(campaignId, peekId ?? '')

  useEffect(() => {
    if (entity && campaignId) {
      addRecent(campaignId, { id: entity.id, name: entity.name, entity_type: entity.entity_type })
    }
  }, [entity, campaignId, addRecent])

  if (!peekId) return null

  const openFull = () => {
    closePeek()
    navigate({ to: '/entities/$entityId', params: { entityId: peekId } })
  }

  return (
    <>
      <div className="peek-scrim" onClick={closePeek} />
      <aside className="peek">
        <div className="peek-head">
          <button className="tag-x" onClick={closePeek} aria-label="close peek">
            ×
          </button>
        </div>
        {!entity && <p className="muted">Loading…</p>}
        {entity && (
          <>
            <h3>
              {entity.name} <span className="badge">{entity.entity_type}</span>
            </h3>
            <p className="muted">{entity.summary ?? 'No summary.'}</p>

            {(entity.tags ?? []).length > 0 && (
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
                {(entity.tags ?? []).map((t) => (
                  <span key={t.id} className="tag">
                    #{t.name}
                  </span>
                ))}
              </div>
            )}

            <p className="muted peek-counts">
              {(entity.outbound ?? []).length} outgoing ·{' '}
              {(entity.backlinks ?? []).length} referenced-by
            </p>

            <button onClick={openFull}>Open full page →</button>
          </>
        )}
      </aside>
    </>
  )
}
