import { useSetStoryNodeStatus, useStorySuggestions } from '../../api/hooks'

interface Props {
  campaignId: string
  onApplied: (lines: string[]) => void
  onSelectNode: (nodeId: string) => void
}

/**
 * What the engine thinks could happen next: beats still `possible` reachable by a satisfied
 * edge from a beat already reached. The engine never fires one itself (FR-4.4) — activation
 * is always the GM's confirmed click.
 */
export function SuggestionsPanel({ campaignId, onApplied, onSelectNode }: Props) {
  const { data: suggestions } = useStorySuggestions(campaignId)
  const setStatus = useSetStoryNodeStatus(campaignId)
  const items = suggestions ?? []

  return (
    <div className="card">
      <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>Suggested next</h3>
      {items.length === 0 && (
        <p className="muted" style={{ fontSize: 12, margin: 0 }}>
          Nothing reachable right now. Activate a beat, or loosen a condition.
        </p>
      )}
      {items.map((s) => (
        <div key={s.node_id} style={{ marginBottom: 10 }}>
          <button className="ghost" style={{ padding: 0 }} onClick={() => onSelectNode(s.node_id)}>
            <strong>{s.name}</strong>
          </button>
          <p className="muted" style={{ fontSize: 12, margin: '2px 0' }}>
            via {s.via_node_name}
            {s.edge_label ? ` · ${s.edge_label}` : ''}
          </p>
          {s.condition_expr && (
            <p className="muted" style={{ fontSize: 11, margin: '2px 0', fontFamily: 'monospace' }}>
              {s.condition_expr}
            </p>
          )}
          <button
            disabled={setStatus.isPending}
            onClick={async () => {
              if (!window.confirm(`Activate "${s.name}"? Its consequences will run.`)) return
              const res = await setStatus.mutateAsync({ nodeId: s.node_id, status: 'active' })
              onApplied(res.applied)
            }}
          >
            Activate
          </button>
        </div>
      ))}
    </div>
  )
}
