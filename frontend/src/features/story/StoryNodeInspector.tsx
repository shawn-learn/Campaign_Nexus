import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useDeleteStoryNode, useSetStoryNodeStatus, useUpdateStoryNode } from '../../api/hooks'
import type { StoryNode } from '../../api/client'
import { ConsequenceEditor } from './ConsequenceEditor'
import { NEXT_STATUS, consequencesOf } from './storyModel'
import type { Consequence } from './storyModel'

interface Props {
  campaignId: string
  node: StoryNode
  onClose: () => void
  onApplied: (lines: string[]) => void
}

export function StoryNodeInspector({ campaignId, node, onClose, onApplied }: Props) {
  const setStatus = useSetStoryNodeStatus(campaignId)
  const update = useUpdateStoryNode(campaignId)
  const del = useDeleteStoryNode(campaignId)

  const [draft, setDraft] = useState<Consequence[]>(consequencesOf(node))
  const [dirty, setDirty] = useState(false)

  // Re-seed when a different beat is selected, or when the server returns new consequences.
  useEffect(() => {
    setDraft(consequencesOf(node))
    setDirty(false)
  }, [node])

  const moves = NEXT_STATUS[node.status] ?? []

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>
          <Link to="/entities/$entityId" params={{ entityId: node.entity_id }}>{node.name}</Link>
        </h3>
        <button className="ghost tag-x" onClick={onClose} aria-label="Close">×</button>
      </div>
      <p className="muted" style={{ fontSize: 12 }}>
        {node.summary ?? 'No summary.'} — name and summary are edited on the wiki page.
      </p>

      <p style={{ margin: '8px 0' }}>
        Status: <strong>{node.status}</strong>
      </p>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap' }}>
        {moves.map((s) => (
          <button
            key={s}
            disabled={setStatus.isPending}
            onClick={async () => {
              const res = await setStatus.mutateAsync({ nodeId: node.entity_id, status: s })
              onApplied(res.applied)
            }}
          >
            → {s}
          </button>
        ))}
        {moves.length === 0 && <span className="muted">No moves from here.</span>}
      </div>
      {setStatus.isError && (
        <p style={{ color: '#e0603a', fontSize: 12 }}>{(setStatus.error as Error).message}</p>
      )}

      <h4 style={{ marginBottom: 4 }}>Consequences</h4>
      <p className="muted" style={{ fontSize: 12, marginTop: 0 }}>
        Run in order when this beat is activated.
      </p>
      <ConsequenceEditor
        campaignId={campaignId}
        value={draft}
        onChange={(next) => {
          setDraft(next)
          setDirty(true)
        }}
        disabled={update.isPending}
      />

      <div className="row" style={{ gap: 6, marginTop: 10 }}>
        <button
          disabled={!dirty || update.isPending}
          onClick={async () => {
            await update.mutateAsync({ nodeId: node.entity_id, consequences: draft })
            setDirty(false)
          }}
        >
          {update.isPending ? 'Saving…' : 'Save consequences'}
        </button>
        {dirty && <span className="muted" style={{ fontSize: 12 }}>Unsaved changes</span>}
      </div>
      {update.isError && (
        <p style={{ color: '#e0603a', fontSize: 12 }}>{(update.error as Error).message}</p>
      )}

      <hr style={{ margin: '12px 0', borderColor: 'var(--border, #333)' }} />
      <button
        className="ghost"
        disabled={del.isPending}
        onClick={() => {
          if (!window.confirm(`Delete the beat "${node.name}"? Its edges go with it.`)) return
          void del.mutateAsync(node.entity_id).then(onClose)
        }}
      >
        Delete beat
      </button>
    </div>
  )
}
