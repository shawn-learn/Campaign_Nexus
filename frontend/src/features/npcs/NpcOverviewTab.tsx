import { useState, useEffect } from 'react'
import type { EntityDetail, Npc } from '../../api/client'
import {
  useUpdateEntity,
  useEntities,
  useRelocateNpc,
  useSetNpcStatus,
  useRecordInteraction,
} from '../../api/hooks'
import { EntityImages } from '../wiki/EntityDetailPage'
import { ShopsKept } from '../merchants/ShopLinks'

const STATUSES = ['alive', 'dead', 'missing', 'unknown', 'retired'] as const

interface NpcOverviewTabProps {
  campaignId: string
  entityId: string
  entity: EntityDetail
  npc: Npc
}

export function NpcOverviewTab({ campaignId, entityId, entity, npc }: NpcOverviewTabProps) {
  const update = useUpdateEntity(campaignId, entityId)
  const { data: locations } = useEntities(campaignId, { entity_type: 'location' })
  const relocate = useRelocateNpc(campaignId)
  const setStatus = useSetNpcStatus(campaignId)
  const interact = useRecordInteraction(campaignId)

  const [name, setName] = useState(entity.name)
  const [summary, setSummary] = useState(entity.summary ?? '')

  useEffect(() => {
    setName(entity.name)
    setSummary(entity.summary ?? '')
  }, [entity])

  const dirty = name !== entity.name || summary !== (entity.summary ?? '')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Quick State Card */}
      <div className="card">
        <h4 style={{ marginTop: 0, marginBottom: 12 }}>Game State Quick Reference</h4>
        <div className="row" style={{ gap: 12, flexWrap: 'wrap', alignItems: 'center' }}>
          <label className="field-inline">
            <span className="muted">Move to</span>
            <select
              value={npc.current_location_id ?? ''}
              onChange={(e) =>
                relocate.mutate({
                  npcId: npc.entity_id,
                  locationId: e.target.value || null,
                  reason: 'GM moved them',
                })
              }
            >
              <option value="">— nowhere —</option>
              {locations?.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field-inline">
            <span className="muted">Status</span>
            <select
              value={npc.status}
              onChange={(e) => setStatus.mutate({ npcId: npc.entity_id, status: e.target.value })}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>

          <button onClick={() => interact.mutate({ npcId: npc.entity_id })}>
            {npc.has_met_party ? 'Record interaction' : 'The party met them'}
          </button>

          {npc.has_met_party && <span className="badge">🤝 Met Party</span>}
          {npc.current_location_name && (
            <span className="badge">📍 {npc.current_location_name}</span>
          )}
          <span className={`badge npc-${npc.status}`}>{npc.status}</span>
        </div>
      </div>

      {/* Name and Summary Card */}
      <div className="card">
        <h4 style={{ marginTop: 0, marginBottom: 12 }}>Details</h4>
        <label className="field">
          <span className="muted">Name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="field">
          <span className="muted">Summary</span>
          <textarea
            rows={3}
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="A one-line description…"
          />
        </label>
        <button
          disabled={!dirty || update.isPending}
          onClick={() =>
            update.mutate({ name, summary: summary || null, summary_set: true })
          }
        >
          {update.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>

      {/* Shops this NPC runs */}
      <ShopsKept campaignId={campaignId} entityId={entityId} />

      {/* Images section */}
      <EntityImages campaignId={campaignId} entityId={entityId} />
    </div>
  )
}
