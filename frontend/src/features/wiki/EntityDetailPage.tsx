import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearch } from '@tanstack/react-router'
import { useRef } from 'react'
import {
  fetchReferences,
  useDeleteEntity,
  useDeleteEntityMedia,
  useEntity,
  useEntityMedia,
  useRestoreEntity,
  useTagEntity,
  useUntagEntity,
  useUpdateEntity,
  useUploadEntityMedia,
  useNpc,
  useMerchant,
  useSkillChallenge,
} from '../../api/hooks'
import type { ReferencesOut } from '../../api/client'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useRecentsStore } from '../../stores/recents'
import { ArticleEditor } from './ArticleEditor'
import { EncounterPanel } from '../playbook/EncounterPanel'
import { RandomTablePanel } from '../playbook/RandomTablePanel'
import { RelationsEditor } from './RelationsEditor'
import type { LinkRef } from '../../api/client'
import { Tabs, TabPanel } from '../../components/Tabs'
import { NpcOverviewTab } from '../npcs/NpcOverviewTab'
import { NpcArticleTab } from '../npcs/NpcArticleTab'
import { NpcGameStateTab } from '../npcs/NpcGameStateTab'
import { NpcSheetTab } from '../npcs/NpcSheetTab'
import { LocationOverviewTab } from './LocationOverviewTab'
import { LocationArticleTab } from './LocationArticleTab'
import { LocationMapTab } from './LocationMapTab'
import { MerchantOverviewTab } from '../merchants/MerchantOverviewTab'
import { BuyTab, SellTab, ManageTab } from '../merchants/ShopTabs'
import {
  SkillChallengeOverviewTab,
  SkillChallengeRunTab,
} from '../playbook/SkillChallengeTabs'

// Entity detail: rename, edit summary, tag/untag, soft-delete/restore.
export function EntityDetailPage() {
  const { entityId } = useParams({ from: '/entities/$entityId' })
  const navigate = useNavigate()
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null

  const { data: entity, isLoading } = useEntity(campaignId, entityId)
  const update = useUpdateEntity(campaignId ?? '', entityId)
  const del = useDeleteEntity(campaignId ?? '')
  const restore = useRestoreEntity(campaignId ?? '')
  const tag = useTagEntity(campaignId ?? '', entityId)
  const untag = useUntagEntity(campaignId ?? '', entityId)
  const { data: npc } = useNpc(campaignId, entity?.entity_type === 'npc' ? entityId : null)
  // A merchant's id *is* its entity id, so the shop record loads straight from entityId.
  const { data: merchant } = useMerchant(
    campaignId,
    entity?.entity_type === 'merchant' ? entityId : null,
  )
  const { data: skillChallenge } = useSkillChallenge(
    campaignId,
    entity?.entity_type === 'skill_challenge' ? entityId : null,
  )

  const [name, setName] = useState('')
  const [summary, setSummary] = useState('')
  const [newTag, setNewTag] = useState('')
  const search = useSearch({ strict: false }) as { tab?: string }
  const [activeTab, setActiveTab] = useState(search.tab ?? 'overview')

  useEffect(() => {
    setActiveTab(search.tab ?? 'overview')
  }, [entityId, search.tab])
  // Delete-preflight (FR-13.3): fetch what points here, then confirm before severing it.
  const [preflight, setPreflight] = useState<ReferencesOut | null>(null)
  const addRecent = useRecentsStore((s) => s.addRecent)

  const askDelete = () => {
    if (!campaignId) return
    void fetchReferences(campaignId, entityId).then(setPreflight)
  }
  const confirmDelete = () => {
    setPreflight(null)
    del.mutate(entityId, { onSuccess: () => navigate({ to: '/entities' }) })
  }

  useEffect(() => {
    if (entity) {
      setName(entity.name)
      setSummary(entity.summary ?? '')
      if (campaignId) {
        addRecent(campaignId, {
          id: entity.id,
          name: entity.name,
          entity_type: entity.entity_type,
        })
      }
    }
  }, [entity, campaignId, addRecent])

  if (isLoading) return <p className="muted">Loading…</p>
  if (!entity) return <p className="muted">Entity not found.</p>

  const dirty = name !== entity.name || summary !== (entity.summary ?? '')

  return (
    <>
      <p className="breadcrumb">
        <Link to="/entities">Entities</Link>
        {(entity.ancestors ?? []).map((a) => (
          <span key={a.entity_id}>
            {' / '}
            <button
              className="linkish"
              onClick={() => navigate({ to: '/entities/$entityId', params: { entityId: a.entity_id } })}
            >
              {a.name}
            </button>
          </span>
        ))}
        {' / '}
        <span className="muted">{entity.name}</span>
      </p>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h2 style={{ margin: 0 }}>
          {entity.name} <span className="badge">{entity.entity_type}</span>
          {entity.deleted && <span className="tag danger">deleted</span>}
        </h2>
        {entity.deleted ? (
          <button onClick={() => restore.mutate(entityId)}>Restore</button>
        ) : (
          <button className="danger-btn" onClick={askDelete}>Delete</button>
        )}
      </div>

      {preflight && (
        <div className="card preflight">
          <h4 style={{ marginTop: 0 }}>Delete “{entity.name}”?</h4>
          {preflight.inbound.length === 0 ? (
            <p className="muted">Nothing references this entity — safe to delete.</p>
          ) : (
            <>
              <p className="muted">
                {preflight.inbound.length} relation(s) point here and will be left dangling:
              </p>
              <ul className="entities">
                {preflight.inbound.map((r) => (
                  <li key={r.link_id}>
                    <button
                      className="linkish"
                      onClick={() =>
                        navigate({ to: '/entities/$entityId', params: { entityId: r.entity_id } })
                      }
                    >
                      {r.name}
                    </button>
                    <span className="badge">{r.label}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="muted" style={{ fontSize: 12 }}>
            This is a soft delete — you can restore it afterwards.
          </p>
          <div className="row" style={{ gap: 6 }}>
            <button className="danger-btn" onClick={confirmDelete}>Delete anyway</button>
            <button className="ghost" onClick={() => setPreflight(null)}>Cancel</button>
          </div>
        </div>
      )}

      {entity.entity_type === 'location' ? (
        <Tabs
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'article', label: 'Article' },
            { id: 'map', label: 'Map' },
          ]}
          activeTab={activeTab}
          onChange={setActiveTab}
        >
          <TabPanel id="overview" activeTab={activeTab}>
            {campaignId && (
              <LocationOverviewTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
              />
            )}
          </TabPanel>
          <TabPanel id="article" activeTab={activeTab}>
            {campaignId && (
              <LocationArticleTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
              />
            )}
          </TabPanel>
          <TabPanel id="map" activeTab={activeTab}>
            {campaignId && (
              <LocationMapTab
                campaignId={campaignId}
                entityId={entityId}
              />
            )}
          </TabPanel>
        </Tabs>
      ) : entity.entity_type === 'skill_challenge' && skillChallenge ? (
        <Tabs
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'article', label: 'Article' },
            { id: 'run', label: 'Run' },
          ]}
          activeTab={activeTab}
          onChange={setActiveTab}
        >
          <TabPanel id="overview" activeTab={activeTab}>
            {campaignId && (
              <SkillChallengeOverviewTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
                challenge={skillChallenge}
              />
            )}
          </TabPanel>
          <TabPanel id="article" activeTab={activeTab}>
            {campaignId && (
              <LocationArticleTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
              />
            )}
          </TabPanel>
          <TabPanel id="run" activeTab={activeTab}>
            {campaignId && (
              <SkillChallengeRunTab campaignId={campaignId} challenge={skillChallenge} />
            )}
          </TabPanel>
        </Tabs>
      ) : entity.entity_type === 'merchant' && merchant ? (
        <Tabs
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'article', label: 'Article' },
            { id: 'buy', label: 'Buy' },
            { id: 'sell', label: 'Sell' },
            { id: 'stock', label: 'Stock' },
          ]}
          activeTab={activeTab}
          onChange={setActiveTab}
        >
          <TabPanel id="overview" activeTab={activeTab}>
            {campaignId && (
              <MerchantOverviewTab
                campaignId={campaignId}
                entityId={entityId}
                merchant={merchant}
              />
            )}
          </TabPanel>
          <TabPanel id="article" activeTab={activeTab}>
            {/* LocationArticleTab is generic — article, relations, links, tags. */}
            {campaignId && (
              <LocationArticleTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
              />
            )}
          </TabPanel>
          <TabPanel id="buy" activeTab={activeTab}>
            {campaignId && <BuyTab campaignId={campaignId} merchantId={entityId} />}
          </TabPanel>
          <TabPanel id="sell" activeTab={activeTab}>
            {campaignId && (
              <SellTab
                campaignId={campaignId}
                merchantId={entityId}
                buyback={merchant.buyback_pct}
              />
            )}
          </TabPanel>
          <TabPanel id="stock" activeTab={activeTab}>
            {campaignId && <ManageTab campaignId={campaignId} merchantId={entityId} />}
          </TabPanel>
        </Tabs>
      ) : entity.entity_type === 'npc' && npc ? (
        <Tabs
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'article', label: 'Article' },
            { id: 'game-state', label: 'Game State' },
            { id: 'sheet', label: 'Sheet' },
          ]}
          activeTab={activeTab}
          onChange={setActiveTab}
        >
          <TabPanel id="overview" activeTab={activeTab}>
            {campaignId && (
              <NpcOverviewTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
                npc={npc}
              />
            )}
          </TabPanel>
          <TabPanel id="article" activeTab={activeTab}>
            {campaignId && (
              <NpcArticleTab
                campaignId={campaignId}
                entityId={entityId}
                entity={entity}
              />
            )}
          </TabPanel>
          <TabPanel id="game-state" activeTab={activeTab}>
            {campaignId && (
              <NpcGameStateTab
                campaignId={campaignId}
                npc={npc}
              />
            )}
          </TabPanel>
          <TabPanel id="sheet" activeTab={activeTab}>
            {campaignId && campaign?.rule_system_id && (
              <NpcSheetTab
                campaignId={campaignId}
                systemId={campaign.rule_system_id}
              />
            )}
          </TabPanel>
        </Tabs>
      ) : (
        <>
          <div className="card">
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

          {campaignId && <EntityImages campaignId={campaignId} entityId={entityId} />}

          {/* Locations are handled by the tabbed branch above; this fallback only
              renders for non-location, non-npc entity types. */}
          {campaignId && entity.entity_type === 'encounter' && (
            <EncounterPanel campaignId={campaignId} entityId={entityId} />
          )}

          {campaignId && entity.entity_type === 'random_table' && (
            <RandomTablePanel campaignId={campaignId} entityId={entityId} />
          )}

          {campaignId && (
            <ArticleEditor
              campaignId={campaignId}
              entityId={entityId}
              initial={entity.article_json ?? null}
              onNavigate={(id) => navigate({ to: '/entities/$entityId', params: { entityId: id } })}
            />
          )}

          {campaignId && (
            <RelationsEditor
              campaignId={campaignId}
              entityId={entityId}
              outbound={entity.outbound ?? []}
              onNavigate={(id) => navigate({ to: '/entities/$entityId', params: { entityId: id } })}
            />
          )}

          <div className="link-panels">
            <LinkPanel
              title="Mentions"
              empty="This article mentions nothing yet."
              links={(entity.outbound ?? []).filter((l) => l.source === 'mention')}
              navigate={navigate}
            />
            <LinkPanel title="Referenced by" empty="Nothing references this yet." links={entity.backlinks ?? []} navigate={navigate} />
          </div>

          <h3>Tags</h3>
          <div className="card">
            <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
              {(entity.tags ?? []).map((t) => (
                <span key={t.id} className="tag">
                  #{t.name}
                  <button className="tag-x" onClick={() => untag.mutate(t.id)} aria-label="remove">
                    ×
                  </button>
                </span>
              ))}
              {(entity.tags ?? []).length === 0 && <span className="muted">No tags yet.</span>}
            </div>
            <form
              className="row"
              onSubmit={(e) => {
                e.preventDefault()
                if (!newTag.trim()) return
                tag.mutate(newTag.trim())
                setNewTag('')
              }}
            >
              <input
                placeholder="Add tag…"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
              />
              <button type="submit" disabled={tag.isPending}>
                Add
              </button>
            </form>
          </div>
        </>
      )}
    </>
  )
}

// A gallery of images attached to the entity. Upload/delete are editor actions; the image
// bytes come from the atlas media store via a per-attachment URL.
export function EntityImages({ campaignId, entityId }: { campaignId: string; entityId: string }) {
  const { data: images } = useEntityMedia(campaignId, entityId)
  const upload = useUploadEntityMedia(campaignId, entityId)
  const del = useDeleteEntityMedia(campaignId, entityId)
  const fileRef = useRef<HTMLInputElement>(null)

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) upload.mutate({ file })
    if (fileRef.current) fileRef.current.value = ''
  }

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>Images</h3>
        <button
          className="ghost"
          disabled={upload.isPending}
          onClick={() => fileRef.current?.click()}
        >
          {upload.isPending ? 'Uploading…' : 'Add image'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/png,image/jpeg,image/gif,image/webp"
          style={{ display: 'none' }}
          onChange={onPick}
        />
      </div>
      {upload.isError && <p className="muted danger">{(upload.error as Error).message}</p>}
      {(images ?? []).length === 0 ? (
        <p className="muted">No images yet.</p>
      ) : (
        <div className="entity-gallery">
          {images!.map((img) => {
            const src = `/api/v1/campaigns/${campaignId}/entities/${entityId}/media/${img.id}/image`
            return (
            <figure key={img.id} className="entity-gallery-item">
              <img
                src={src}
                alt={img.caption ?? img.filename}
                loading="lazy"
                title="Double-click to open full size in a new tab"
                onDoubleClick={() => window.open(src, '_blank', 'noopener,noreferrer')}
              />
              <button
                className="tag-x gallery-del"
                aria-label="delete image"
                onClick={() => del.mutate(img.id)}
              >
                ×
              </button>
              {img.caption && <figcaption className="muted">{img.caption}</figcaption>}
            </figure>
            )
          })}
        </div>
      )}
    </div>
  )
}

export function LinkPanel({
  title,
  empty,
  links,
  navigate,
}: {
  title: string
  empty: string
  links: LinkRef[]
  navigate: ReturnType<typeof useNavigate>
}) {
  return (
    <div className="card link-panel">
      <h4>{title}</h4>
      {links.length === 0 && <p className="muted">{empty}</p>}
      <ul>
        {links.map((l) => (
          <li key={l.link_id}>
            <button
              className="linkish"
              onClick={() => navigate({ to: '/entities/$entityId', params: { entityId: l.entity_id } })}
            >
              {l.name}
            </button>
            <span className="badge">{l.entity_type}</span>
            {l.deleted && <span className="tag danger">deleted</span>}
          </li>
        ))}
      </ul>
    </div>
  )
}
