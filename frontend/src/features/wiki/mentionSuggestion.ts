// @mention autocomplete for the Tiptap editor. Searches campaign entities and offers a
// "create-in-place" row (the red-link loop) when nothing matches — selecting it creates
// the entity and links it without leaving the editor (Sprint 3 exit criterion).
import type { Editor } from '@tiptap/react'
import { searchEntities } from '../../api/hooks'
import type { Entity } from '../../api/client'

interface MentionItem {
  id: string
  label: string
}

interface SuggestionProps {
  items: Entity[]
  command: (item: MentionItem) => void
  clientRect?: (() => DOMRect | null) | null
  query: string
  editor: Editor
}

interface KeyDownProps {
  event: KeyboardEvent
}

interface BuildParams {
  campaignId: string
  // Creates an entity for the typed name and returns its mention attrs.
  createEntity: (name: string) => Promise<MentionItem>
}

// A minimal floating list rendered into document.body (no tippy dependency).
class MentionPopup {
  private el: HTMLDivElement
  private index = 0
  private props: SuggestionProps
  private createEntity: (name: string) => Promise<MentionItem>

  constructor(props: SuggestionProps, createEntity: (name: string) => Promise<MentionItem>) {
    this.props = props
    this.createEntity = createEntity
    this.el = document.createElement('div')
    this.el.className = 'mention-popup'
    document.body.appendChild(this.el)
    this.render(props)
  }

  private rowCount(): number {
    // entity hits + one "create" row when a query is present
    return this.props.items.length + (this.props.query.trim() ? 1 : 0)
  }

  private isCreateRow(i: number): boolean {
    return i >= this.props.items.length
  }

  render(props: SuggestionProps): void {
    this.props = props
    if (this.index >= this.rowCount()) this.index = 0
    this.el.innerHTML = ''

    props.items.forEach((hit, i) => {
      const row = document.createElement('button')
      row.type = 'button'
      row.className = 'mention-item' + (i === this.index ? ' active' : '')
      row.innerHTML = `<span>${escapeHtml(hit.name)}</span><span class="mention-type">${hit.entity_type}</span>`
      row.onmousedown = (e) => {
        e.preventDefault()
        void this.select(i)
      }
      this.el.appendChild(row)
    })

    if (props.query.trim()) {
      const i = props.items.length
      const row = document.createElement('button')
      row.type = 'button'
      row.className = 'mention-item mention-create' + (i === this.index ? ' active' : '')
      row.innerHTML = `<span>+ Create “${escapeHtml(props.query.trim())}”</span><span class="mention-type">note</span>`
      row.onmousedown = (e) => {
        e.preventDefault()
        void this.select(i)
      }
      this.el.appendChild(row)
    }

    if (this.rowCount() === 0) {
      this.el.innerHTML = '<div class="mention-empty">Type to search…</div>'
    }
    this.position(props)
  }

  private position(props: SuggestionProps): void {
    const rect = props.clientRect?.()
    if (!rect) return
    this.el.style.top = `${rect.bottom + window.scrollY + 4}px`
    this.el.style.left = `${rect.left + window.scrollX}px`
  }

  private async select(i: number): Promise<void> {
    if (this.isCreateRow(i)) {
      const item = await this.createEntity(this.props.query.trim())
      this.props.command(item)
    } else {
      const hit = this.props.items[i]
      this.props.command({ id: hit.id, label: hit.name })
    }
  }

  onKeyDown({ event }: KeyDownProps): boolean {
    const n = this.rowCount()
    if (event.key === 'ArrowDown') {
      this.index = n === 0 ? 0 : (this.index + 1) % n
      this.render(this.props)
      return true
    }
    if (event.key === 'ArrowUp') {
      this.index = n === 0 ? 0 : (this.index - 1 + n) % n
      this.render(this.props)
      return true
    }
    if (event.key === 'Enter') {
      if (n > 0) void this.select(this.index)
      return true
    }
    if (event.key === 'Escape') return true
    return false
  }

  destroy(): void {
    this.el.remove()
  }
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] ?? c,
  )
}

export function buildMentionSuggestion({ campaignId, createEntity }: BuildParams) {
  return {
    items: async ({ query }: { query: string }) => searchEntities(campaignId, query),
    render: () => {
      let popup: MentionPopup | null = null
      return {
        onStart: (props: SuggestionProps) => {
          popup = new MentionPopup(props, createEntity)
        },
        onUpdate: (props: SuggestionProps) => popup?.render(props),
        onKeyDown: (props: KeyDownProps) => popup?.onKeyDown(props) ?? false,
        onExit: () => {
          popup?.destroy()
          popup = null
        },
      }
    },
  }
}
