import { useEffect, useState } from 'react'
import { useCreateStoryEdge, useDeleteStoryEdge } from '../../api/hooks'
import type { StoryEdge, StoryNode } from '../../api/client'
import { ConditionField } from './ConditionField'

interface Props {
  campaignId: string
  edge: StoryEdge
  nodes: StoryNode[]
  onClose: () => void
  onReplaced: (edge: StoryEdge) => void
}

export function StoryEdgeInspector({ campaignId, edge, nodes, onClose, onReplaced }: Props) {
  const create = useCreateStoryEdge(campaignId)
  const del = useDeleteStoryEdge(campaignId)

  const [condition, setCondition] = useState(edge.condition_expr ?? '')
  const [label, setLabel] = useState(edge.label ?? '')

  useEffect(() => {
    setCondition(edge.condition_expr ?? '')
    setLabel(edge.label ?? '')
  }, [edge])

  const nameOf = (id: string) => nodes.find((n) => n.entity_id === id)?.name ?? id
  const dirty = condition !== (edge.condition_expr ?? '') || label !== (edge.label ?? '')
  const busy = create.isPending || del.isPending

  // The backend exposes no PATCH for edges (story/router.py) — an edit is a delete followed
  // by a create, which mints a new id. Delete first so the pair never both exist. The created
  // edge is handed straight back to the parent: the graph query has not necessarily refetched
  // yet, so looking the new id up in the cached graph would find the deleted one.
  const save = async () => {
    await del.mutateAsync(edge.id)
    const replacement = await create.mutateAsync({
      from_node: edge.from_node,
      to_node: edge.to_node,
      condition_expr: condition.trim() || null,
      label: label.trim() || null,
    })
    onReplaced(replacement)
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0, fontSize: 15 }}>
          {nameOf(edge.from_node)} → {nameOf(edge.to_node)}
        </h3>
        <button className="ghost tag-x" onClick={onClose} aria-label="Close">×</button>
      </div>

      <div style={{ marginTop: 8 }}>
        <label className="muted" style={{ fontSize: 12 }}>Label</label>
        <input value={label} onChange={(e) => setLabel(e.target.value)} style={{ width: '100%' }} />
      </div>

      <div style={{ marginTop: 8 }}>
        <ConditionField campaignId={campaignId} value={condition} onChange={setCondition} />
      </div>

      <div className="row" style={{ gap: 6, marginTop: 10 }}>
        <button disabled={!dirty || busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button
          className="ghost"
          disabled={busy}
          onClick={() => {
            if (!window.confirm('Delete this transition?')) return
            void del.mutateAsync(edge.id).then(onClose)
          }}
        >
          Delete transition
        </button>
      </div>
      {(create.isError || del.isError) && (
        <p style={{ color: '#e0603a', fontSize: 12 }}>
          {((create.error ?? del.error) as Error).message}
        </p>
      )}
    </div>
  )
}
