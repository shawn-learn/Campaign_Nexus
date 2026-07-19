import { useState } from 'react'
import {
  useCreateStoryEdge,
  useCreateStoryNode,
  useStoryGraph,
  useUpdateStoryNode,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { FlagsPanel } from './FlagsPanel'
import { StoryEdgeInspector } from './StoryEdgeInspector'
import { StoryGraphCanvas } from './StoryGraphCanvas'
import { StoryNodeInspector } from './StoryNodeInspector'
import { SuggestionsPanel } from './SuggestionsPanel'
import { autoArrange, needsAutoArrange } from './storyModel'

type Selection = { kind: 'node' | 'edge'; id: string } | null

/**
 * The story graph (FR-4): the GM authors beats and the conditional transitions between them,
 * and the engine reports which beats are reachable now. Nothing fires without confirmation.
 */
export function StoryPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: graph, isLoading } = useStoryGraph(campaignId)
  const createNode = useCreateStoryNode(campaignId ?? '')
  const createEdge = useCreateStoryEdge(campaignId ?? '')
  const updateNode = useUpdateStoryNode(campaignId ?? '')

  const [selected, setSelected] = useState<Selection>(null)
  const [applied, setApplied] = useState<string[] | null>(null)
  const [name, setName] = useState('')

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>
  if (isLoading || !graph) return <p className="muted">Loading story graph…</p>

  const cid = campaign.id
  const selectedNode =
    selected?.kind === 'node' ? graph.nodes.find((n) => n.entity_id === selected.id) ?? null : null
  const selectedEdge =
    selected?.kind === 'edge' ? graph.edges.find((e) => e.id === selected.id) ?? null : null

  const add = async () => {
    if (!name.trim()) return
    // Stagger new beats so they don't stack at the origin before the GM arranges them.
    const offset = graph.nodes.length * 30
    const node = await createNode.mutateAsync({
      name: name.trim(),
      status: 'possible',
      pos_x: 40 + offset,
      pos_y: 40 + offset,
      consequences: [],
    })
    setName('')
    setSelected({ kind: 'node', id: node.entity_id })
  }

  const arrange = () => {
    const positions = autoArrange(graph.nodes, graph.edges)
    Object.entries(positions).forEach(([id, p]) =>
      updateNode.mutate({ nodeId: id, pos_x: p.x, pos_y: p.y }),
    )
  }

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Story</h2>
        <div className="row" style={{ gap: 6 }}>
          <input
            value={name}
            placeholder="New beat name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && void add()}
          />
          <button disabled={!name.trim() || createNode.isPending} onClick={() => void add()}>
            Add beat
          </button>
          {needsAutoArrange(graph.nodes) && (
            <button className="ghost" onClick={arrange}>Auto-arrange</button>
          )}
        </div>
      </div>

      {applied && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <strong style={{ fontSize: 13 }}>
              {applied.length === 0 ? 'Beat updated — no consequences to run.' : 'Consequences applied'}
            </strong>
            <button className="ghost tag-x" onClick={() => setApplied(null)} aria-label="Dismiss">×</button>
          </div>
          {applied.length > 0 && (
            <ul style={{ margin: '6px 0 0', fontSize: 12 }}>
              {applied.map((line, i) => <li key={i}>{line}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          <StoryGraphCanvas
            graph={graph}
            selectedId={selected?.id ?? null}
            onSelectNode={(id) => setSelected({ kind: 'node', id })}
            onSelectEdge={(id) => setSelected({ kind: 'edge', id })}
            onMoveNode={(id, x, y) => updateNode.mutate({ nodeId: id, pos_x: x, pos_y: y })}
            onConnectNodes={(from, to) =>
              createEdge.mutate({ from_node: from, to_node: to, condition_expr: null, label: null })
            }
          />
          {graph.nodes.length > 0 && (
            <p className="muted" style={{ fontSize: 12 }}>
              Drag beats to arrange · drag between handles to add a transition · click a beat or
              transition to edit it. Dashed edges carry a condition.
            </p>
          )}
        </div>

        <div style={{ flex: '0 0 320px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <SuggestionsPanel
            campaignId={cid}
            onApplied={setApplied}
            onSelectNode={(id) => setSelected({ kind: 'node', id })}
          />
          {selectedNode && (
            <StoryNodeInspector
              campaignId={cid}
              node={selectedNode}
              onClose={() => setSelected(null)}
              onApplied={setApplied}
            />
          )}
          {selectedEdge && (
            <StoryEdgeInspector
              campaignId={cid}
              edge={selectedEdge}
              nodes={graph.nodes}
              onClose={() => setSelected(null)}
              // Saving recreates the edge under a new id; follow the selection to it.
              onReplaced={(next) => setSelected({ kind: 'edge', id: next.id })}
            />
          )}
          <FlagsPanel campaignId={cid} flags={graph.flags as Record<string, unknown>} />
        </div>
      </div>
    </>
  )
}
