import { useEffect, useState } from 'react'
import type { EntityDetail } from '../../api/client'
import { useUpdateEntity } from '../../api/hooks'
import { EntityImages } from './EntityDetailPage'
import { ShopsHere } from '../merchants/ShopLinks'
import { EncountersHere } from '../playbook/EncounterLinks'

interface LocationOverviewTabProps {
  campaignId: string
  entityId: string
  entity: EntityDetail
}

export function LocationOverviewTab({ campaignId, entityId, entity }: LocationOverviewTabProps) {
  const update = useUpdateEntity(campaignId, entityId)
  const [name, setName] = useState(entity.name)
  const [summary, setSummary] = useState(entity.summary ?? '')

  useEffect(() => {
    setName(entity.name)
    setSummary(entity.summary ?? '')
  }, [entity])

  const dirty = name !== entity.name || summary !== (entity.summary ?? '')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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

      {/* Shops with this location as their storefront */}
      <ShopsHere campaignId={campaignId} entityId={entityId} />

      {/* Encounters staged here */}
      <EncountersHere backlinks={entity.backlinks ?? []} />

      {/* Snapped Images Gallery */}
      <EntityImages campaignId={campaignId} entityId={entityId} />
    </div>
  )
}
