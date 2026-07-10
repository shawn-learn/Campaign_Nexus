import { useMemo } from 'react'
import ReactFlow, { Background, Controls, MarkerType, Position } from 'reactflow'
import type { Edge, Node } from 'reactflow'
import 'reactflow/dist/style.css'
import dagre from 'dagre'
import type { QuestGraph } from '../../api/client'

// The quest dependency DAG (FR-10.4, ADR-009): React Flow renders, dagre lays out. The view
// is read-only — dependencies are edited on the board, so there is no node-drag to persist.
const NODE_W = 190
const NODE_H = 48

const STATUS_COLOR: Record<string, string> = {
  unknown: '#6b6b76',
  available: '#5aa6e0',
  active: '#e0b64e',
  completed: '#6fce7a',
  failed: '#e0603a',
  expired: '#a05fc6',
  abandoned: '#4d4d57',
}

/** Left-to-right layout: prerequisites sit left of the quests they unlock. */
function layout(nodes: Node[], edges: Edge[]): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 70 })
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map((n) => {
    const { x, y } = g.node(n.id)
    // dagre centers nodes; React Flow positions by top-left corner.
    return { ...n, position: { x: x - NODE_W / 2, y: y - NODE_H / 2 } }
  })
}

export function QuestGraphView({
  graph,
  onSelect,
}: {
  graph: QuestGraph
  onSelect: (questId: string) => void
}) {
  const { nodes, edges } = useMemo(() => {
    const rawNodes: Node[] = graph.nodes.map((q) => ({
      id: q.id,
      data: {
        label: `${q.overdue ? '⌛ ' : ''}${q.name}`,
      },
      position: { x: 0, y: 0 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        width: NODE_W,
        height: NODE_H,
        borderRadius: 8,
        border: `2px solid ${STATUS_COLOR[q.status] ?? '#6b6b76'}`,
        background: 'var(--panel)',
        color: 'var(--text)',
        fontSize: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        opacity: q.status === 'completed' ? 0.65 : 1,
      },
    }))
    const rawEdges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed },
      style: { stroke: '#6b6b76' },
    }))
    return { nodes: layout(rawNodes, rawEdges), edges: rawEdges }
  }, [graph])

  if (graph.nodes.length === 0) {
    return <p className="muted">No quests to graph yet.</p>
  }

  return (
    <div className="quest-graph card" style={{ height: 460, padding: 0 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        onNodeClick={(_e, n) => onSelect(n.id)}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
