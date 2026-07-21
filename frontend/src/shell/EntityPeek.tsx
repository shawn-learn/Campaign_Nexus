import { useEffect } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { useEntity, useEntityMedia } from '../api/hooks'
import { useUiStore } from '../stores/ui'
import { useRecentsStore } from '../stores/recents'
import { useActiveCampaign } from './useActiveCampaign'
import { ArticleView } from '../features/wiki/ArticleView'

interface LinkRef {
  link_id: string
  entity_id: string
  name: string
  entity_type: string
}

// A list of neighbours. Clicking one swaps the peek to that entity rather than
// navigating, so following links never loses the screen behind the panel.
function PeekLinks({
  title,
  links,
  onPeek,
}: {
  title: string
  links: LinkRef[]
  onPeek: (entityId: string) => void
}) {
  if (links.length === 0) return null
  return (
    <div className="peek-section">
      <h4>
        {title} <span className="muted">({links.length})</span>
      </h4>
      <ul className="peek-links">
        {links.map((l) => (
          <li key={l.link_id}>
            <button className="linkish" onClick={() => onPeek(l.entity_id)}>
              {l.name}
            </button>
            <span className="badge">{l.entity_type}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Entity peek: a side panel that shows a compact view without leaving the current
// screen (docs/12, §12.1 "peek, then commit"). Second action = open the full page.
export function EntityPeek() {
  const peekId = useUiStore((s) => s.peekId)
  const openPeek = useUiStore((s) => s.openPeek)
  const closePeek = useUiStore((s) => s.closePeek)
  const navigate = useNavigate()
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const addRecent = useRecentsStore((s) => s.addRecent)

  const { data: entity } = useEntity(campaignId, peekId ?? '')
  const { data: images } = useEntityMedia(campaignId, peekId)

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

  const outbound = (entity?.outbound ?? []) as LinkRef[]
  const backlinks = (entity?.backlinks ?? []) as LinkRef[]

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

            {(images ?? []).length > 0 && (
              <div className="peek-gallery">
                {images!.map((img) => {
                  const src = `/api/v1/campaigns/${campaignId}/entities/${peekId}/media/${img.id}/image`
                  return (
                    <img
                      key={img.id}
                      src={src}
                      alt={img.caption ?? img.filename}
                      loading="lazy"
                      title="Double-click to open full size in a new tab"
                      onDoubleClick={() => window.open(src, '_blank', 'noopener,noreferrer')}
                    />
                  )
                })}
              </div>
            )}

            <div className="peek-section">
              <h4>Article</h4>
              <ArticleView
                content={entity.article_json ?? null}
                onNavigate={(id) => openPeek(id)}
              />
            </div>

            <PeekLinks title="Links to" links={outbound} onPeek={openPeek} />
            <PeekLinks title="Referenced by" links={backlinks} onPeek={openPeek} />

            <button onClick={openFull}>Open full page →</button>
          </>
        )}
      </aside>
    </>
  )
}
