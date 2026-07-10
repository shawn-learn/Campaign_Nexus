import { useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import type { Content, JSONContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Mention from '@tiptap/extension-mention'
import { useQueryClient } from '@tanstack/react-query'
import {
  createEntityRequest,
  useArticleSnapshots,
  useRestoreArticleSnapshot,
  useUpdateArticle,
} from '../../api/hooks'
import { buildMentionSuggestion } from './mentionSuggestion'

interface Props {
  campaignId: string
  entityId: string
  initial: Record<string, unknown> | null
  onNavigate: (entityId: string) => void
}

// Rich-text article editor. @mentions are first-class nodes; on save the server diffs
// them into typed links (FR-2.2/2.3). Autosaves ~800 ms after the last keystroke.
export function ArticleEditor({ campaignId, entityId, initial, onNavigate }: Props) {
  const qc = useQueryClient()
  const save = useUpdateArticle(campaignId, entityId)
  const [status, setStatus] = useState<'idle' | 'dirty' | 'saving' | 'saved'>('idle')
  const [showHistory, setShowHistory] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Article version history (FR-13.4) — only fetched while the panel is open.
  const { data: snapshots } = useArticleSnapshots(campaignId, entityId, showHistory)
  const restoreSnapshot = useRestoreArticleSnapshot(campaignId, entityId)

  const createEntity = async (name: string) => {
    const created = await createEntityRequest(campaignId, 'note', name)
    void qc.invalidateQueries({ queryKey: ['entities', campaignId] })
    return { id: created.id, label: created.name }
  }

  const editor = useEditor({
    extensions: [
      StarterKit,
      Mention.configure({
        HTMLAttributes: { class: 'mention' },
        renderText: ({ node }) => `@${node.attrs.label ?? node.attrs.id}`,
        suggestion: buildMentionSuggestion({ campaignId, createEntity }),
      }),
    ],
    content: (initial as Content) ?? '',
    editorProps: {
      handleClickOn: (_view, _pos, node) => {
        if (node.type.name === 'mention' && typeof node.attrs.id === 'string') {
          onNavigate(node.attrs.id)
          return true
        }
        return false
      },
    },
    onUpdate: () => {
      setStatus('dirty')
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => void doSave(), 800)
    },
  })

  const doSave = async () => {
    if (!editor) return
    setStatus('saving')
    await save.mutateAsync(editor.getJSON() as Record<string, unknown>)
    setStatus('saved')
  }

  // Reset content when navigating between entities.
  useEffect(() => {
    if (editor) {
      editor.commands.setContent((initial as JSONContent) ?? '')
      setStatus('idle')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId])

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current)
  }, [])

  return (
    <div className="article">
      <div className="article-toolbar">
        <span className="muted">
          Article — type <code>@</code> to mention
        </span>
        <span className="row" style={{ gap: 10 }}>
          <span className="article-status muted">
            {status === 'saving' && 'Saving…'}
            {status === 'saved' && 'Saved'}
            {status === 'dirty' && 'Unsaved…'}
          </span>
          <button className="linkish" onClick={() => setShowHistory((v) => !v)}>
            {showHistory ? 'Hide history' : 'History'}
          </button>
        </span>
      </div>

      {showHistory && (
        <div className="card article-history">
          {(snapshots ?? []).length === 0 && (
            <p className="muted">No earlier versions yet — they accrue as you edit.</p>
          )}
          {snapshots?.map((s) => (
            <div key={s.id} className="row" style={{ justifyContent: 'space-between' }}>
              <span className="muted" title={s.created_at_real}>
                {s.preview || '(empty)'}
              </span>
              <button
                className="ghost"
                disabled={restoreSnapshot.isPending}
                onClick={() =>
                  restoreSnapshot.mutate(s.id, {
                    onSuccess: (detail) => {
                      editor?.commands.setContent(
                        (detail.article_json as JSONContent | null) ?? '',
                      )
                      setShowHistory(false)
                    },
                  })
                }
              >
                Restore
              </button>
            </div>
          ))}
        </div>
      )}

      <EditorContent editor={editor} className="article-body" />
    </div>
  )
}
