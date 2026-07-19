// Pure model for the story graph — no React, no network, so the rules that matter (legal
// transitions, the closed consequence catalog, layout) stay unit-testable.
import dagre from 'dagre'
import type { StoryEdge, StoryNode } from '../../api/client'

export const NODE_W = 200
export const NODE_H = 52

// Mirrors the quest graph's palette (QuestGraphView.tsx) so the two graphs read alike.
export const STATUS_COLOR: Record<string, string> = {
  possible: '#6b6b76',
  active: '#e0b64e',
  resolved: '#6fce7a',
  abandoned: '#4d4d57',
}

// The backend's transition table (story/service.py:43). Rendering only these means an
// illegal move — and its 409 — is unreachable from the UI.
export const NEXT_STATUS: Record<string, string[]> = {
  possible: ['active', 'abandoned'],
  active: ['resolved', 'abandoned'],
  resolved: ['active'],
  abandoned: ['possible'],
}

/** How a consequence parameter is edited. Entity kinds resolve against the wiki. */
export type ParamKind = 'flag-key' | 'flag-value' | 'text' | 'entity:quest' | 'entity:npc' | 'entity:location'

export interface ParamSpec {
  key: string
  label: string
  kind: ParamKind
  optional?: boolean
}

export interface ConsequenceSpec {
  action: string
  label: string
  params: ParamSpec[]
}

// The closed catalog from story/consequences.py:22. Described as data so the editor renders
// fields from a table rather than a six-branch switch — adding an action here is enough.
export const CONSEQUENCE_SPECS: ConsequenceSpec[] = [
  {
    action: 'set_flag',
    label: 'Set flag',
    params: [
      { key: 'key', label: 'Flag key', kind: 'flag-key' },
      { key: 'value', label: 'Value', kind: 'flag-value' },
    ],
  },
  {
    action: 'activate_quest',
    label: 'Activate quest',
    params: [{ key: 'quest_id', label: 'Quest', kind: 'entity:quest' }],
  },
  {
    action: 'complete_quest',
    label: 'Complete quest',
    params: [{ key: 'quest_id', label: 'Quest', kind: 'entity:quest' }],
  },
  {
    action: 'fail_quest',
    label: 'Fail quest',
    params: [{ key: 'quest_id', label: 'Quest', kind: 'entity:quest' }],
  },
  {
    action: 'relocate_npc',
    label: 'Relocate NPC',
    params: [
      { key: 'npc_id', label: 'NPC', kind: 'entity:npc' },
      { key: 'location_id', label: 'To location', kind: 'entity:location', optional: true },
    ],
  },
  {
    action: 'narrate',
    label: 'Narrate',
    params: [{ key: 'text', label: 'Text', kind: 'text' }],
  },
]

export const SPEC_BY_ACTION: Record<string, ConsequenceSpec> = Object.fromEntries(
  CONSEQUENCE_SPECS.map((s) => [s.action, s]),
)

/** The API types consequences as an open record; narrow at this single boundary. */
export type Consequence = Record<string, unknown>

export function consequencesOf(node: StoryNode): Consequence[] {
  return (node.consequences ?? []) as Consequence[]
}

/** A one-line summary for node badges and the inspector list. */
export function describeConsequence(c: Consequence): string {
  const action = String(c.action ?? '?')
  switch (action) {
    case 'set_flag':
      return `set flag ${String(c.key ?? '?')} = ${JSON.stringify(c.value ?? true)}`
    case 'activate_quest':
    case 'complete_quest':
    case 'fail_quest':
      return `${action.replace('_', ' ')} ${String(c.quest_id ?? '?')}`
    case 'relocate_npc':
      return c.location_id
        ? `relocate NPC ${String(c.npc_id ?? '?')} → ${String(c.location_id)}`
        : `relocate NPC ${String(c.npc_id ?? '?')}`
    case 'narrate': {
      const text = String(c.text ?? '')
      return `narrate: ${text.length > 40 ? `${text.slice(0, 40)}…` : text}`
    }
    default:
      return action
  }
}

/** Build a blank consequence with every required param present but empty. */
export function blankConsequence(action: string): Consequence {
  const spec = SPEC_BY_ACTION[action]
  const c: Consequence = { action }
  spec?.params.forEach((p) => {
    if (!p.optional) c[p.key] = p.kind === 'flag-value' ? true : ''
  })
  return c
}

/** True when no beat has ever been positioned, so an auto-layout is safe to offer. */
export function needsAutoArrange(nodes: StoryNode[]): boolean {
  return nodes.length > 1 && nodes.every((n) => n.pos_x === 0 && n.pos_y === 0)
}

/**
 * Left-to-right dagre layout, returning new positions per node id. Unlike the quest graph
 * this runs once on demand — story positions are persisted, so we must not re-derive them
 * on every render or the GM's manual arrangement would be discarded.
 */
export function autoArrange(
  nodes: StoryNode[],
  edges: StoryEdge[],
): Record<string, { x: number; y: number }> {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: 'LR', nodesep: 30, ranksep: 90 })
  nodes.forEach((n) => g.setNode(n.entity_id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => {
    // dagre throws on edges referencing unknown nodes; the graph query keeps these in sync,
    // but guard so one stale edge cannot blank the whole canvas.
    if (g.hasNode(e.from_node) && g.hasNode(e.to_node)) g.setEdge(e.from_node, e.to_node)
  })
  dagre.layout(g)
  const out: Record<string, { x: number; y: number }> = {}
  nodes.forEach((n) => {
    const { x, y } = g.node(n.entity_id)
    // dagre centers nodes; React Flow positions by top-left corner.
    out[n.entity_id] = { x: x - NODE_W / 2, y: y - NODE_H / 2 }
  })
  return out
}
