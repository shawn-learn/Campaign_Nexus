import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  useMaps,
  useMap,
  useSetMapLocation,
  useParty,
  usePatchParty,
  useUploadMap,
  useEntities,
} from '../../api/hooks'
import { MapCanvas } from '../atlas/MapCanvasComponents'
import type { MapSummary } from '../../api/client'

interface LocationMapTabProps {
  campaignId: string
  entityId: string
}

export function LocationMapTab({ campaignId, entityId }: LocationMapTabProps) {
  const navigate = useNavigate()
  const { data: maps } = useMaps(campaignId)
  const setLocation = useSetMapLocation(campaignId)
  const { data: party } = useParty(campaignId)
  const patchParty = usePatchParty(campaignId)
  const uploadMap = useUploadMap(campaignId)

  // Filter maps Snapped to this location
  const attached = useMemo(
    () => (maps ?? []).filter((m) => m.location_id === entityId),
    [maps, entityId],
  )

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [edit, setEdit] = useState(false)
  const [showUpload, setShowUpload] = useState(false)

  // Upload form state
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploadName, setUploadName] = useState('')
  const [uploadKind, setUploadKind] = useState('region')
  const [uploadDesc, setUploadDesc] = useState('')
  const [uploadErr, setUploadErr] = useState<string | null>(null)

  const shownId =
    selectedId && attached.some((m) => m.entity_id === selectedId)
      ? selectedId
      : attached[0]?.entity_id ?? null

  const { data: detail } = useMap(campaignId, shownId)

  const isPartyHere = party?.current_location_id === entityId

  // Reset manual selection when map is detached
  useEffect(() => {
    if (selectedId && !attached.some((m) => m.entity_id === selectedId)) {
      setSelectedId(null)
    }
  }, [attached, selectedId])

  if (maps === undefined) return <p className="muted">Loading maps…</p>

  const handleUploadSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const file = fileRef.current?.files?.[0]
    if (!file || !uploadName.trim()) return
    setUploadErr(null)

    uploadMap.mutate(
      {
        file,
        name: uploadName.trim(),
        mapKind: uploadKind,
        description: uploadDesc.trim() || null,
      },
      {
        onSuccess: (newMap) => {
          // Auto-associate the new map with this location
          setLocation.mutate(
            { mapId: newMap.entity_id, locationId: entityId },
            {
              onSuccess: () => {
                setSelectedId(newMap.entity_id)
                setUploadName('')
                setUploadDesc('')
                setShowUpload(false)
                if (fileRef.current) fileRef.current.value = ''
              },
            }
          )
        },
        onError: (err) => setUploadErr((err as Error).message),
      }
    )
  }

  // Handle drill down pin click
  const handleDrill = (childMapId: string, _childMapName: string) => {
    const targetMap = maps.find((m) => m.entity_id === childMapId)
    if (targetMap?.location_id) {
      // Navigate to child map's location Map tab
      navigate({
        to: '/entities/$entityId',
        params: { entityId: targetMap.location_id },
        search: { tab: 'map' },
      })
    } else {
      // No linked location: just snap inside this tab if they want to view it, or direct link
      setSelectedId(childMapId)
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header controls card */}
      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 10 }}>
          <div className="row" style={{ gap: 10, alignItems: 'center' }}>
            <h3 style={{ margin: 0 }}>Location Maps</h3>
            {party && (
              isPartyHere ? (
                <span className="tag success" style={{ fontSize: 11, padding: '2px 6px' }}>📍 Party is here</span>
              ) : (
                <button
                  className="ghost"
                  style={{ fontSize: 11, padding: '2px 6px', border: '1px solid var(--border)' }}
                  disabled={patchParty.isPending}
                  onClick={() => patchParty.mutate({ current_location_id: entityId, location_set: true })}
                >
                  📍 Move Party Here
                </button>
              )
            )}
          </div>

          <div className="row" style={{ gap: 8 }}>
            {shownId && (
              <>
                <button className={edit ? '' : 'ghost'} onClick={() => setEdit((e) => !e)}>
                  {edit ? 'Done Editing' : '✏️ Edit Pins'}
                </button>
                <button
                  className="ghost tag-x"
                  disabled={setLocation.isPending}
                  onClick={() => setLocation.mutate({ mapId: shownId, locationId: '' })}
                >
                  Detach Map
                </button>
              </>
            )}
            <button className="ghost" onClick={() => setShowUpload(!showUpload)}>
              {showUpload ? 'Cancel Upload' : '➕ Upload New Map'}
            </button>
          </div>
        </div>

        {/* Upload Form */}
        {showUpload && (
          <form onSubmit={handleUploadSubmit} style={{ marginTop: 16, borderTop: '1px solid var(--border)', paddingTop: 16 }}>
            <h4 style={{ marginTop: 0, marginBottom: 12 }}>Upload & Snapping Map</h4>
            <div className="row" style={{ gap: 10, flexWrap: 'wrap', marginBottom: 8 }}>
              <input ref={fileRef} type="file" accept="image/png,image/jpeg,image/gif,image/webp" required />
              <input placeholder="Map name" value={uploadName} onChange={(e) => setUploadName(e.target.value)} required />
              <select value={uploadKind} onChange={(e) => setUploadKind(e.target.value)}>
                <option value="world">world</option>
                <option value="region">region</option>
                <option value="city">city</option>
                <option value="dungeon">dungeon</option>
                <option value="building">building</option>
              </select>
              <button type="submit" disabled={uploadMap.isPending || setLocation.isPending}>
                {uploadMap.isPending ? 'Uploading…' : 'Upload & Snap'}
              </button>
            </div>
            <textarea
              value={uploadDesc}
              onChange={(e) => setUploadDesc(e.target.value)}
              placeholder="Description (optional)"
              rows={2}
              style={{ width: '100%' }}
            />
            {uploadErr && <p className="tag danger" style={{ marginTop: 8 }}>{uploadErr}</p>}
          </form>
        )}

        {/* Attached Map switching tabs */}
        {attached.length > 1 && (
          <div className="row layer-chips" style={{ gap: 6, marginTop: 12, borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <span className="muted" style={{ fontSize: 11, alignSelf: 'center' }}>Layers:</span>
            {attached.map((m) => (
              <button
                key={m.entity_id}
                className={'chip' + (m.entity_id === shownId ? '' : ' off')}
                onClick={() => setSelectedId(m.entity_id)}
              >
                {m.name}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Attach Picker for existing maps */}
      {!shownId && !showUpload && (
        <div className="card">
          <p className="muted" style={{ marginBottom: 12 }}>No maps currently snap to this location.</p>
          <AttachPicker
            campaignId={campaignId}
            maps={maps}
            attached={attached}
            onAttach={(mapId) => {
              setLocation.mutate(
                { mapId, locationId: entityId },
                { onSuccess: () => setSelectedId(mapId) },
              )
            }}
            pending={setLocation.isPending}
          />
        </div>
      )}

      {/* Map Canvas */}
      {shownId && detail && (
        <MapCanvas
          key={detail.entity_id}
          campaignId={campaignId}
          detail={detail}
          edit={edit}
          onDrill={handleDrill}
        />
      )}
      {shownId && !detail && <p className="muted">Loading map details…</p>}
    </div>
  )
}

function AttachPicker({
  campaignId,
  maps,
  attached,
  onAttach,
  pending,
}: {
  campaignId: string
  maps: MapSummary[]
  attached: MapSummary[]
  onAttach: (mapId: string) => void
  pending: boolean
}) {
  const [picking, setPicking] = useState(false)
  const [choice, setChoice] = useState('')
  const { data: locations } = useEntities(picking ? campaignId : null, { entity_type: 'location' })

  const attachedIds = new Set(attached.map((m) => m.entity_id))
  const candidates = maps.filter((m) => !attachedIds.has(m.entity_id))

  if (candidates.length === 0 && attached.length === 0) {
    return <p className="muted" style={{ fontSize: 12 }}>No maps uploaded yet. Use the upload button above to add one.</p>
  }
  if (candidates.length === 0) return null

  if (!picking) {
    return (
      <button onClick={() => setPicking(true)}>
        Attach Existing Map
      </button>
    )
  }

  const ownerLabel = (m: MapSummary) => {
    if (!m.location_id) return ''
    const owner = locations?.find((l) => l.id === m.location_id)?.name
    return owner ? ` — snaps to ${owner}` : ' — snaps elsewhere'
  }

  return (
    <form
      className="row"
      style={{ gap: 6 }}
      onSubmit={(e) => {
        e.preventDefault()
        if (!choice) return
        onAttach(choice)
        setPicking(false)
        setChoice('')
      }}
    >
      <select value={choice} onChange={(e) => setChoice(e.target.value)}>
        <option value="">— choose a map —</option>
        {candidates.map((m) => (
          <option key={m.entity_id} value={m.entity_id}>
            {m.name} ({m.map_kind}){ownerLabel(m)}
          </option>
        ))}
      </select>
      <button type="submit" disabled={!choice || pending}>Attach</button>
      <button type="button" className="ghost" onClick={() => setPicking(false)}>Cancel</button>
    </form>
  )
}
