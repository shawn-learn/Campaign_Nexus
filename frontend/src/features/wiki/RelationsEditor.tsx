import { useEffect, useState } from 'react'
import {
  searchEntities,
  useCreateLink,
  useDeleteLink,
  useLinkTypes,
} from '../../api/hooks'
import type { Entity, LinkRef } from '../../api/client'

interface Props {
  campaignId: string
  entityId: string
  outbound: LinkRef[] // full outbound set; we render only explicit relations here
  onNavigate: (entityId: string) => void
}

// Explicit typed-relations editor (FR-2.4). Mentions are managed by the article and
// shown separately; this handles GM-asserted edges (within, member_of, located_at…).
export function RelationsEditor({ campaignId, entityId, outbound, onNavigate }: Props) {
  const { data: linkTypes } = useLinkTypes(campaignId)
  const createLink = useCreateLink(campaignId, entityId)
  const deleteLink = useDeleteLink(campaignId)

  const [typeId, setTypeId] = useState('within')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Entity[]>([])
  const [target, setTarget] = useState<Entity | null>(null)
  const [error, setError] = useState<string | null>(null)

  const explicit = outbound.filter((l) => l.source === 'explicit')

  useEffect(() => {
    if (!query.trim() || target) {
      setResults([])
      return
    }
    let live = true
    void searchEntities(campaignId, query.trim()).then((hits) => {
      if (live) setResults(hits.filter((h) => h.id !== entityId).slice(0, 6))
    })
    return () => {
      live = false
    }
  }, [query, target, campaignId, entityId])

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!target) return
    createLink.mutate(
      { to_entity: target.id, link_type_id: typeId },
      {
        onSuccess: () => {
          setTarget(null)
          setQuery('')
        },
        onError: (err) => setError(err.message),
      },
    )
  }

  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>Relations</h3>

      <ul className="relations">
        {explicit.map((l) => (
          <li key={l.link_id}>
            <span className="rel-label">{l.label}</span>
            <button className="linkish" onClick={() => onNavigate(l.entity_id)}>
              {l.name}
            </button>
            <span className="badge">{l.entity_type}</span>
            <button
              className="tag-x"
              aria-label="remove relation"
              onClick={() => deleteLink.mutate(l.link_id)}
            >
              ×
            </button>
          </li>
        ))}
        {explicit.length === 0 && <p className="muted">No relations yet.</p>}
      </ul>

      <form className="relation-form" onSubmit={submit}>
        <div className="row">
          <select value={typeId} onChange={(e) => setTypeId(e.target.value)}>
            {linkTypes?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.label}
              </option>
            ))}
          </select>
          {target ? (
            <span className="chosen-target">
              {target.name}
              <button
                type="button"
                className="tag-x"
                onClick={() => setTarget(null)}
                aria-label="clear"
              >
                ×
              </button>
            </span>
          ) : (
            <input
              placeholder="Search target entity…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          )}
          <button type="submit" disabled={!target || createLink.isPending}>
            Link
          </button>
        </div>

        {results.length > 0 && !target && (
          <ul className="picker">
            {results.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => setTarget(r)}>
                  <span>{r.name}</span>
                  <span className="mention-type">{r.entity_type}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {error && <p className="error-text">{error}</p>}
      </form>
    </div>
  )
}
