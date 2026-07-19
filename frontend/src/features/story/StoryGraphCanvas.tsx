import { useEffect, useMemo } from 'react'
import ReactFlow, { Background, Controls, MarkerType, Position, useEdgesState, useNodesState } from 'reactflow'
import type { Connection, Edge, Node } from 'reactflow'
import 'reactflow/dist/style.css'
import type { StoryGraph } from '../../api/client'
import { NODE_H, NODE_W, STATUS_COLOR, consequencesOf } from './storyModel'

interface Props {
  graph: StoryGraph
  selectedId: string | null
  onSelectNode: (nodeId: string) => void
  onSelectEdge: (edgeId: string) => void
  onMoveNode: (nodeId: string, x: number, y: number) => void
  onConnectNodes: (from: string, to: string) => void
}

/**
 * The beat graph. Unlike the read-only quest DAG, positions here are persisted server-side,
 * so nodes are draggable and the layout is authored rather than derived. Drag persistence
 * hangs off `onNodeDragStop` — it fires exactly once per gesture, which is naturally
 * debounced and avoids a write per animation frame.
 */
export function StoryGraphCanvas({
  graph,
  selectedId,
  onSelectNode,
  onSelectEdge,
  onMoveNode,
  onConnectNodes,
}: Props) {
  const { rfNodes, rfEdges } = useMemo(() => {
    const nodes: Node[] = graph.nodes.map((n) => {
      const count = consequencesOf(n).length
      const color = STATUS_COLOR[n.status] ?? STATUS_COLOR.possible
      return {
        id: n.entity_id,
        data: { label: count > 0 ? `${n.name}  ⚙${count}` : n.name },
        position: { x: n.pos_x, y: n.pos_y },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
        style: {
          width: NODE_W,
          height: NODE_H,
          borderRadius: 8,
          border: `2px solid ${color}`,
          outline: n.entity_id === selectedId ? '2px solid var(--accent, #8ab4f8)' : undefined,
          background: 'var(--panel)',
          color: 'var(--text)',
          fontSize: 12,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center' as const,
          padding: 4,
          opacity: n.status === 'abandoned' ? 0.55 : 1,
        },
      }
    })
    const edges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.from_node,
      target: e.to_node,
      // The condition is the load-bearing detail — show it even when a label exists.
      label: [e.label, e.condition_expr].filter(Boolean).join('  ·  ') || undefined,
      labelStyle: { fill: 'var(--text)', fontSize: 10 },
      labelBgStyle: { fill: 'var(--panel)' },
      markerEnd: { type: MarkerType.ArrowClosed },
      style: {
        stroke: e.id === selectedId ? 'var(--accent, #8ab4f8)' : '#6b6b76',
        strokeWidth: e.id === selectedId ? 2 : 1,
        // A conditional edge is dashed, so gated branches read at a glance.
        strokeDasharray: e.condition_expr ? '6 3' : undefined,
      },
    }))
    return { rfNodes: nodes, rfEdges: edges }
  }, [graph, selectedId])

  const [nodes, setNodes, onNodesChange] = useNodesState(rfNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(rfEdges)

  // Re-seed from the server whenever the graph query returns new data. Position writes
  // intentionally do not invalidate that query, so this does not fire mid-drag.
  useEffect(() => setNodes(rfNodes), [rfNodes, setNodes])
  useEffect(() => setEdges(rfEdges), [rfEdges, setEdges])

  if (graph.nodes.length === 0) {
    return <p className="muted">No beats yet. Add one to start mapping the story.</p>
  }

  return (
    <div className="story-graph card" style={{ height: 560, padding: 0 }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStop={(_e, n) => onMoveNode(n.id, n.position.x, n.position.y)}
        onConnect={(c: Connection) => {
          if (c.source && c.target && c.source !== c.target) onConnectNodes(c.source, c.target)
        }}
        onNodeClick={(_e, n) => onSelectNode(n.id)}
        onEdgeClick={(_e, e) => onSelectEdge(e.id)}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={16} size={1} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
