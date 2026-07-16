import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import type { EntityDetail } from '../../api/client'
import { useTagEntity, useUntagEntity } from '../../api/hooks'
import { ArticleEditor } from './ArticleEditor'
import { RelationsEditor } from './RelationsEditor'
import { LinkPanel } from './EntityDetailPage'

interface LocationArticleTabProps {
  campaignId: string
  entityId: string
  entity: EntityDetail
}

export function LocationArticleTab({ campaignId, entityId, entity }: LocationArticleTabProps) {
  const navigate = useNavigate()
  const tag = useTagEntity(campaignId, entityId)
  const untag = useUntagEntity(campaignId, entityId)
  const [newTag, setNewTag] = useState('')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Article Editor */}
      <ArticleEditor
        campaignId={campaignId}
        entityId={entityId}
        initial={entity.article_json ?? null}
        onNavigate={(id) => navigate({ to: '/entities/$entityId', params: { entityId: id } })}
      />

      {/* Relations Editor */}
      <RelationsEditor
        campaignId={campaignId}
        entityId={entityId}
        outbound={entity.outbound ?? []}
        onNavigate={(id) => navigate({ to: '/entities/$entityId', params: { entityId: id } })}
      />

      {/* Mentions & Referenced By Panels */}
      <div className="link-panels">
        <LinkPanel
          title="Mentions"
          empty="This article mentions nothing yet."
          links={(entity.outbound ?? []).filter((l) => l.source === 'mention')}
          navigate={navigate}
        />
        <LinkPanel
          title="Referenced by"
          empty="Nothing references this yet."
          links={entity.backlinks ?? []}
          navigate={navigate}
        />
      </div>

      {/* Tags section */}
      <h3>Tags</h3>
      <div className="card">
        <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
          {(entity.tags ?? []).map((t) => (
            <span key={t.id} className="tag">
              #{t.name}
              <button className="tag-x" onClick={() => untag.mutate(t.id)} aria-label="remove">
                ×
              </button>
            </span>
          ))}
          {(entity.tags ?? []).length === 0 && <span className="muted">No tags yet.</span>}
        </div>
        <form
          className="row"
          onSubmit={(e) => {
            e.preventDefault()
            if (!newTag.trim()) return
            tag.mutate(newTag.trim())
            setNewTag('')
          }}
        >
          <input
            placeholder="Add tag…"
            value={newTag}
            onChange={(e) => setNewTag(e.target.value)}
          />
          <button type="submit" disabled={tag.isPending}>
            Add
          </button>
        </form>
      </div>
    </div>
  )
}
