import { describe, expect, it } from 'vitest'
import type { StoryEdge, StoryNode } from '../../api/client'
import {
  CONSEQUENCE_SPECS,
  NEXT_STATUS,
  autoArrange,
  blankConsequence,
  describeConsequence,
  needsAutoArrange,
} from './storyModel'

function node(id: string, over: Partial<StoryNode> = {}): StoryNode {
  return {
    entity_id: id,
    name: id,
    summary: null,
    status: 'possible',
    pos_x: 0,
    pos_y: 0,
    consequences: [],
    ...over,
  }
}

function edge(from: string, to: string): StoryEdge {
  return { id: `${from}->${to}`, from_node: from, to_node: to, condition_expr: null, label: null }
}

describe('NEXT_STATUS', () => {
  // Must match backend story/service.py:43 — the UI only renders legal moves, so a drift
  // here would surface to the GM as an unexplained 409.
  it('mirrors the backend transition table', () => {
    expect(NEXT_STATUS).toEqual({
      possible: ['active', 'abandoned'],
      active: ['resolved', 'abandoned'],
      resolved: ['active'],
      abandoned: ['possible'],
    })
  })

  it('never offers a transition to the status a beat already holds', () => {
    for (const [from, tos] of Object.entries(NEXT_STATUS)) expect(tos).not.toContain(from)
  })
})

describe('CONSEQUENCE_SPECS', () => {
  it('covers exactly the backend catalog', () => {
    expect(CONSEQUENCE_SPECS.map((s) => s.action).sort()).toEqual(
      ['activate_quest', 'complete_quest', 'fail_quest', 'narrate', 'relocate_npc', 'set_flag'].sort(),
    )
  })

  it('builds a blank carrying every required param', () => {
    expect(blankConsequence('set_flag')).toEqual({ action: 'set_flag', key: '', value: true })
    // location_id is optional on relocate_npc, so it stays absent until chosen.
    expect(blankConsequence('relocate_npc')).toEqual({ action: 'relocate_npc', npc_id: '' })
  })
})

describe('describeConsequence', () => {
  it('summarizes each action', () => {
    expect(describeConsequence({ action: 'set_flag', key: 'x', value: true })).toBe(
      'set flag x = true',
    )
    expect(describeConsequence({ action: 'activate_quest', quest_id: 'q1' })).toBe(
      'activate quest q1',
    )
    expect(describeConsequence({ action: 'relocate_npc', npc_id: 'n1', location_id: 'l1' })).toBe(
      'relocate NPC n1 → l1',
    )
  })

  it('truncates long narration', () => {
    expect(describeConsequence({ action: 'narrate', text: 'a'.repeat(60) })).toBe(
      `narrate: ${'a'.repeat(40)}…`,
    )
  })
})

describe('needsAutoArrange', () => {
  it('is true only when every beat is still unpositioned', () => {
    expect(needsAutoArrange([node('a'), node('b')])).toBe(true)
    expect(needsAutoArrange([node('a'), node('b', { pos_x: 10 })])).toBe(false)
    expect(needsAutoArrange([node('a')])).toBe(false) // nothing to arrange
    expect(needsAutoArrange([])).toBe(false)
  })
})

describe('autoArrange', () => {
  it('lays successors out to the right of their predecessor', () => {
    const pos = autoArrange([node('a'), node('b')], [edge('a', 'b')])
    expect(pos.b.x).toBeGreaterThan(pos.a.x)
  })

  it('ignores edges referencing unknown nodes rather than throwing', () => {
    expect(() => autoArrange([node('a')], [edge('a', 'ghost')])).not.toThrow()
  })
})
