// TanStack Query hooks over the typed client. Mutations invalidate the affected
// queries so views stay fresh without manual refetching (FR-14.3).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './client'
import type { CampaignCreate, EntityCreate, EntityUpdate } from './client'

function unwrap<T>(result: { data?: T; error?: unknown }, msg: string): T {
  if (result.error || result.data === undefined) {
    // FastAPI problem responses carry a human-readable `detail`; surface it.
    const detail = (result.error as { detail?: unknown } | undefined)?.detail
    throw new Error(typeof detail === 'string' ? detail : msg)
  }
  return result.data
}

// --- campaigns --------------------------------------------------------------
export function useCampaigns() {
  return useQuery({
    queryKey: ['campaigns'],
    queryFn: async () => unwrap(await api.GET('/api/v1/campaigns'), 'load campaigns'),
  })
}

export function useRuleSystems() {
  return useQuery({
    queryKey: ['rule-systems'],
    queryFn: async () => unwrap(await api.GET('/api/v1/rule-systems'), 'load rule systems'),
  })
}

export function useCreateCampaign() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: CampaignCreate) =>
      unwrap(await api.POST('/api/v1/campaigns', { body }), 'create campaign'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['campaigns'] }),
  })
}

// --- entities ---------------------------------------------------------------
interface EntityFilters {
  entity_type?: string
  tag_id?: string
  include_deleted?: boolean
}

export function useEntities(campaignId: string | null, filters: EntityFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['entities', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/entities', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load entities',
      ),
  })
}

export function useEntity(campaignId: string | null, entityId: string) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['entity', campaignId, entityId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/entities/{entity_id}', {
          params: { path: { campaign_id: campaignId!, entity_id: entityId } },
        }),
        'load entity',
      ),
  })
}

// Invalidate everything derived from a campaign's world state after a write.
function invalidateCampaign(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['entities', campaignId] })
  void qc.invalidateQueries({ queryKey: ['entity', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['tags', campaignId] })
}

export function useCreateEntity(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: EntityCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/entities', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

export function useUpdateEntity(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: EntityUpdate) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/entities/{entity_id}', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
          body,
        }),
        'update entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

export function useDeleteEntity(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (entityId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/entities/{entity_id}', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
        }),
        'delete entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

export function useRestoreEntity(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (entityId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/restore', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
        }),
        'restore entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

// --- tags -------------------------------------------------------------------
export function useTagEntity(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/tags', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
          body: { name },
        }),
        'tag entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

export function useUntagEntity(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tagId: string) =>
      unwrap(
        await api.DELETE(
          '/api/v1/campaigns/{campaign_id}/entities/{entity_id}/tags/{tag_id}',
          { params: { path: { campaign_id: campaignId, entity_id: entityId, tag_id: tagId } } },
        ),
        'untag entity',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

// --- article (mentions -> links) --------------------------------------------
export function useUpdateArticle(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (article_json: Record<string, unknown>) =>
      unwrap(
        await api.PUT('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/article', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
          body: { article_json },
        }),
        'save article',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

// Imperative entity search for the @mention picker (runs outside React render).
export async function searchEntities(campaignId: string, q: string) {
  const { data } = await api.GET('/api/v1/campaigns/{campaign_id}/entities', {
    params: { path: { campaign_id: campaignId }, query: { q } },
  })
  return data ?? []
}

// Ranked FTS search for the ⌘K command palette.
export async function searchEntitiesFts(campaignId: string, q: string, limit = 15) {
  const { data } = await api.GET('/api/v1/campaigns/{campaign_id}/search', {
    params: { path: { campaign_id: campaignId }, query: { q, limit } },
  })
  return data ?? []
}

export async function createEntityRequest(
  campaignId: string,
  entity_type: string,
  name: string,
) {
  const { data, error } = await api.POST('/api/v1/campaigns/{campaign_id}/entities', {
    params: { path: { campaign_id: campaignId } },
    body: { entity_type, name },
  })
  if (error || !data) throw new Error('create entity')
  return data
}

// --- links (explicit relations) ---------------------------------------------
export function useLinkTypes(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['link-types', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/link-types', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load link types',
      ),
  })
}

export function useCreateLink(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { to_entity: string; link_type_id: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/links', {
          params: { path: { campaign_id: campaignId, entity_id: entityId } },
          body,
        }),
        'create link',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

export function useDeleteLink(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (linkId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/links/{link_id}', {
          params: { path: { campaign_id: campaignId, link_id: linkId } },
        }),
        'delete link',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

// --- time engine ------------------------------------------------------------
export function useClock(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['clock', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/clock', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load clock',
      ),
  })
}

export function useSetRealtime(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (enabled: boolean) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/clock/realtime', {
          params: { path: { campaign_id: campaignId } },
          body: { enabled },
        }),
        'set realtime',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['clock', campaignId] }),
  })
}

export function useAdvanceTime(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { days?: number; hours?: number; minutes?: number; reason?: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/clock/advance', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'advance time',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
      void qc.invalidateQueries({ queryKey: ['events', campaignId] })
      void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] })
      void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
    },
  })
}

// --- scheduled events -------------------------------------------------------
export function useScheduledEvents(campaignId: string | null, statusFilter?: string) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['scheduled-events', campaignId, statusFilter],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/scheduled-events', {
          params: {
            path: { campaign_id: campaignId! },
            query: statusFilter ? { status_filter: statusFilter } : {},
          },
        }),
        'load scheduled events',
      ),
  })
}

export function useCreateScheduledEvent(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      title: string
      fire_at_game: number
      action_type: string
      action_json?: Record<string, unknown>
      recurrence_days?: number | null
    }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/scheduled-events', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create scheduled event',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] }),
  })
}

export function useCancelScheduledEvent(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (eventId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/scheduled-events/{event_id}',
        { params: { path: { campaign_id: campaignId, event_id: eventId } } },
      )
      if (error) throw new Error('cancel scheduled event')
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] }),
  })
}

export async function previewAdvance(
  campaignId: string,
  body: { days?: number; hours?: number },
) {
  const { data } = await api.POST('/api/v1/campaigns/{campaign_id}/clock/advance/preview', {
    params: { path: { campaign_id: campaignId } },
    body,
  })
  return data ?? null
}

// --- rules / stat blocks ----------------------------------------------------
export async function fetchSheetLayout(systemId: string, sheetType: string) {
  const { data } = await api.GET('/api/v1/rule-systems/{system_id}/layout/{sheet_type}', {
    params: { path: { system_id: systemId, sheet_type: sheetType } },
  })
  return data ?? null
}

export function useSheetLayout(systemId: string | null, sheetType: string) {
  return useQuery({
    enabled: !!systemId,
    queryKey: ['sheet-layout', systemId, sheetType],
    queryFn: async () => fetchSheetLayout(systemId!, sheetType),
  })
}

export function useStatBlocks(campaignId: string | null, sheetType?: string) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['stat-blocks', campaignId, sheetType],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/stat-blocks', {
          params: {
            path: { campaign_id: campaignId! },
            query: sheetType ? { sheet_type: sheetType } : {},
          },
        }),
        'load stat blocks',
      ),
  })
}

interface StatBlockError {
  detail?: { errors?: string[] }
}

export function useCreateStatBlock(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      rule_system_id: string
      sheet_type: string
      label: string
      doc: Record<string, unknown>
    }) => {
      const { data, error } = await api.POST('/api/v1/campaigns/{campaign_id}/stat-blocks', {
        params: { path: { campaign_id: campaignId } },
        body,
      })
      if (error || !data) {
        const errs = (error as StatBlockError | undefined)?.detail?.errors
        throw new Error(errs?.join('; ') ?? 'create stat block')
      }
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['stat-blocks', campaignId] }),
  })
}

export function useUpdateStatBlock(campaignId: string, blockId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { label?: string; doc: Record<string, unknown> }) => {
      const { data, error } = await api.PUT(
        '/api/v1/campaigns/{campaign_id}/stat-blocks/{block_id}',
        { params: { path: { campaign_id: campaignId, block_id: blockId } }, body },
      )
      if (error || !data) {
        const errs = (error as StatBlockError | undefined)?.detail?.errors
        throw new Error(errs?.join('; ') ?? 'update stat block')
      }
      return data
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['stat-blocks', campaignId] }),
  })
}

// --- party ------------------------------------------------------------------
export function useParty(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['party', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/party', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load party',
      ),
  })
}

function invalidateParty(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['party', campaignId] })
  void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
}

export function usePatchParty(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { gold?: number }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/party', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'update party',
      ),
    onSuccess: () => invalidateParty(qc, campaignId),
  })
}

export function useAddPartyMember(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (statBlockId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/party/members', {
          params: { path: { campaign_id: campaignId } },
          body: { stat_block_id: statBlockId },
        }),
        'add member',
      ),
    onSuccess: () => invalidateParty(qc, campaignId),
  })
}

export function useRest(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    // The rest names come from the campaign's rule system (PartyOut.rest_types), not from us.
    mutationFn: async (restType: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/party/rest', {
          params: { path: { campaign_id: campaignId } },
          body: { rest_type: restType },
        }),
        'rest',
      ),
    onSuccess: () => invalidateParty(qc, campaignId),
  })
}

// --- combat -----------------------------------------------------------------
export async function startCombat(campaignId: string, encounterId: string) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/combats', {
      params: { path: { campaign_id: campaignId } },
      body: { encounter_id: encounterId },
    }),
    'start combat',
  )
}

export async function combatAction(
  campaignId: string,
  runId: string,
  actionType: string,
  payload: Record<string, unknown>,
) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions', {
      params: { path: { campaign_id: campaignId, run_id: runId } },
      body: { action_type: actionType, payload },
    }),
    'combat action',
  )
}

export async function getCombat(campaignId: string, runId: string) {
  return unwrap(
    await api.GET('/api/v1/campaigns/{campaign_id}/combats/{run_id}', {
      params: { path: { campaign_id: campaignId, run_id: runId } },
    }),
    'load combat',
  )
}

export async function combatUndo(campaignId: string, runId: string) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/undo', {
      params: { path: { campaign_id: campaignId, run_id: runId } },
    }),
    'undo',
  )
}

export async function combatRedo(campaignId: string, runId: string) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/redo', {
      params: { path: { campaign_id: campaignId, run_id: runId } },
    }),
    'redo',
  )
}

export async function endCombat(campaignId: string, runId: string) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/end', {
      params: { path: { campaign_id: campaignId, run_id: runId } },
    }),
    'end combat',
  )
}

// --- import / export --------------------------------------------------------
export async function exportBestiary(campaignId: string) {
  const { data } = await api.GET('/api/v1/campaigns/{campaign_id}/monsters/export', {
    params: { path: { campaign_id: campaignId } },
  })
  return data
}

export async function importBestiary(campaignId: string, payload: unknown) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/monsters/import-json', {
      params: { path: { campaign_id: campaignId } },
      body: payload as Record<string, never>,
    }),
    'import bestiary',
  ) as { imported: number; errors: string[] }
}

export async function exportCampaign(campaignId: string) {
  const { data } = await api.GET('/api/v1/campaigns/{campaign_id}/export', {
    params: { path: { campaign_id: campaignId } },
  })
  return data
}

export async function importCampaign(payload: unknown) {
  const { data, error } = await api.POST('/api/v1/campaigns/import', {
    body: payload as Record<string, never>,
  })
  if (error || !data) throw new Error('import failed — is this a campaign archive?')
  return data
}

// --- encounters -------------------------------------------------------------
export function useEncounters(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['encounters', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/encounters', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load encounters',
      ),
  })
}

interface CombatantSpec {
  monster_id: string
  count: number
  side?: string
}

export function useCreateEncounter(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      name: string
      terrain?: string | null
      combatants: CombatantSpec[]
      location_id?: string | null
    }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/encounters', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create encounter',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['encounters', campaignId] })
      void qc.invalidateQueries({ queryKey: ['entity', campaignId] })
    },
  })
}

// --- bestiary ---------------------------------------------------------------
interface MonsterFilters {
  q?: string
  facet1_num_gte?: number
  facet1_num_lte?: number
  facet1_text?: string
}

export function useMonsters(campaignId: string | null, filters: MonsterFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['monsters', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/monsters', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load monsters',
      ),
  })
}

export function useFacetManifest(systemId: string | null) {
  return useQuery({
    enabled: !!systemId,
    queryKey: ['facets', systemId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/rule-systems/{system_id}/facets', {
          params: { path: { system_id: systemId! } },
        }),
        'load facets',
      ),
  })
}

export function useMakeVariant(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (monsterId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/monsters/{monster_id}/variant', {
          params: { path: { campaign_id: campaignId, monster_id: monsterId } },
        }),
        'create variant',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['monsters', campaignId] }),
  })
}

// --- timeline ---------------------------------------------------------------
interface TimelineFilters {
  session_id?: string
  entity_id?: string
  from_game?: number
  to_game?: number
  significance_min?: number
  include_hidden?: boolean
}

export function useTimeline(campaignId: string | null, filters: TimelineFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['timeline', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/timeline', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load timeline',
      ),
  })
}

export function useCreateManualEntry(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      title: string
      body?: string | null
      occurred_at_game: number
      significance?: number
      entity_ids?: string[]
    }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/timeline/manual', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create timeline entry',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['timeline', campaignId] }),
  })
}

// --- sessions ---------------------------------------------------------------
export function useSessions(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['sessions', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/sessions', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load sessions',
      ),
  })
}

export function useSessionDetail(campaignId: string | null, sessionId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!sessionId,
    queryKey: ['session', campaignId, sessionId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/sessions/{session_id}', {
          params: { path: { campaign_id: campaignId!, session_id: sessionId! } },
        }),
        'load session',
      ),
  })
}

function invalidateSessions(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['sessions', campaignId] })
  void qc.invalidateQueries({ queryKey: ['session', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
}

export function useCreateSession(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/sessions', {
          params: { path: { campaign_id: campaignId } },
          body: {},
        }),
        'create session',
      ),
    onSuccess: () => invalidateSessions(qc, campaignId),
  })
}

export function useSessionAction(campaignId: string, action: 'start' | 'end') {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (sessionId: string) => {
      const path =
        action === 'start'
          ? ('/api/v1/campaigns/{campaign_id}/sessions/{session_id}/start' as const)
          : ('/api/v1/campaigns/{campaign_id}/sessions/{session_id}/end' as const)
      return unwrap(
        await api.POST(path, {
          params: { path: { campaign_id: campaignId, session_id: sessionId } },
        }),
        `${action} session`,
      )
    },
    onSuccess: () => invalidateSessions(qc, campaignId),
  })
}

export function useCaptureNote(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (textBody: string) => {
      const { error } = await api.POST('/api/v1/campaigns/{campaign_id}/notes', {
        params: { path: { campaign_id: campaignId } },
        body: { text: textBody },
      })
      if (error) throw new Error('capture note')
    },
    onSuccess: () => {
      invalidateSessions(qc, campaignId)
      void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
    },
  })
}

// --- live session dashboard (FR-14) -----------------------------------------
export function useDashboard(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    // Kept fresh by the shared realtime tick (ClockWidget invalidates ['clock']);
    // we also refetch on window focus so returning to the tab reflects mid-session edits.
    queryKey: ['dashboard', campaignId],
    refetchOnWindowFocus: true,
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/views/dashboard', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load dashboard',
      ),
  })
}

export function useSetDashboardLocation(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (entityId: string | null) =>
      unwrap(
        await api.PUT('/api/v1/campaigns/{campaign_id}/views/dashboard/location', {
          params: { path: { campaign_id: campaignId } },
          body: { entity_id: entityId },
        }),
        'set location',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] }),
  })
}

export function useSetDashboardPin(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { entityId: string; pinned: boolean }) =>
      unwrap(
        await api.PUT('/api/v1/campaigns/{campaign_id}/views/dashboard/pins', {
          params: { path: { campaign_id: campaignId } },
          body: { entity_id: vars.entityId, pinned: vars.pinned },
        }),
        'set pin',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] }),
  })
}

// --- atlas: interactive maps (FR-3) -----------------------------------------
export function useMaps(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['maps', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/maps', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load maps',
      ),
  })
}

export function useMap(campaignId: string | null, mapId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!mapId,
    queryKey: ['map', campaignId, mapId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/maps/{map_id}', {
          params: { path: { campaign_id: campaignId!, map_id: mapId! } },
        }),
        'load map',
      ),
  })
}

// Multipart upload bypasses the JSON client; on success it hands back the new map's id.
export function useUploadMap(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      file: File
      name: string
      mapKind: string
      locationId?: string | null
      parentMapId?: string | null
    }) => {
      const fd = new FormData()
      fd.append('file', vars.file)
      fd.append('name', vars.name)
      fd.append('map_kind', vars.mapKind)
      if (vars.locationId) fd.append('location_id', vars.locationId)
      if (vars.parentMapId) fd.append('parent_map_id', vars.parentMapId)
      const res = await fetch(`/api/v1/campaigns/${campaignId}/maps`, {
        method: 'POST',
        body: fd,
      })
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({})))?.detail
        throw new Error(typeof detail === 'string' ? detail : 'upload map')
      }
      return (await res.json()) as import('./client').MapDetail
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['maps', campaignId] }),
  })
}

export function useDeleteMap(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (mapId: string) => {
      const { error } = await api.DELETE('/api/v1/campaigns/{campaign_id}/maps/{map_id}', {
        params: { path: { campaign_id: campaignId, map_id: mapId } },
      })
      if (error) throw new Error('delete map')
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['maps', campaignId] }),
  })
}

interface MarkerInput {
  x: number
  y: number
  icon?: string | null
  color?: string | null
  note?: string | null
  layer?: string
  target_entity_id?: string | null
  child_map_id?: string | null
}

function invalidateMap(qc: ReturnType<typeof useQueryClient>, campaignId: string, mapId: string) {
  void qc.invalidateQueries({ queryKey: ['map', campaignId, mapId] })
  void qc.invalidateQueries({ queryKey: ['maps', campaignId] })
}

export function useAddMarker(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: MarkerInput) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/maps/{map_id}/markers', {
          params: { path: { campaign_id: campaignId, map_id: mapId } },
          body,
        }),
        'add marker',
      ),
    onSuccess: () => invalidateMap(qc, campaignId, mapId),
  })
}

export function useUpdateMarker(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { markerId: string; patch: Partial<MarkerInput> }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/maps/{map_id}/markers/{marker_id}', {
          params: {
            path: { campaign_id: campaignId, map_id: mapId, marker_id: vars.markerId },
          },
          body: vars.patch,
        }),
        'update marker',
      ),
    onSuccess: () => invalidateMap(qc, campaignId, mapId),
  })
}

export function useDeleteMarker(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (markerId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/maps/{map_id}/markers/{marker_id}',
        { params: { path: { campaign_id: campaignId, map_id: mapId, marker_id: markerId } } },
      )
      if (error) throw new Error('delete marker')
    },
    onSuccess: () => invalidateMap(qc, campaignId, mapId),
  })
}

interface RegionInput {
  name?: string | null
  polygon: [number, number][]
  color?: string | null
  note?: string | null
  layer?: string
  target_entity_id?: string | null
  child_map_id?: string | null
}

export function useAddRegion(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RegionInput) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/maps/{map_id}/regions', {
          params: { path: { campaign_id: campaignId, map_id: mapId } },
          body,
        }),
        'add region',
      ),
    onSuccess: () => invalidateMap(qc, campaignId, mapId),
  })
}

export function useDeleteRegion(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (regionId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/maps/{map_id}/regions/{region_id}',
        { params: { path: { campaign_id: campaignId, map_id: mapId, region_id: regionId } } },
      )
      if (error) throw new Error('delete region')
    },
    onSuccess: () => invalidateMap(qc, campaignId, mapId),
  })
}

// --- quests (FR-10) ---------------------------------------------------------
export function useQuests(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['quests', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/quests', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load quests',
      ),
  })
}

export function useQuestGraph(campaignId: string | null, enabled = true) {
  return useQuery({
    enabled: !!campaignId && enabled,
    queryKey: ['quest-graph', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/quests/graph', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load quest graph',
      ),
  })
}

// A quest write can move the clock's scheduled events, the timeline and the dashboard.
function invalidateQuests(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['quests', campaignId] })
  void qc.invalidateQueries({ queryKey: ['quest-graph', campaignId] })
  void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
  void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
}

export function useCreateQuest(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      name: string
      summary?: string | null
      quest_type?: string
      status?: string
      deadline_game?: number | null
      objectives?: { text: string; done?: boolean }[]
    }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/quests', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create quest',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

export function useSetQuestStatus(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { questId: string; status: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/quests/{quest_id}/status', {
          params: { path: { campaign_id: campaignId, quest_id: vars.questId } },
          body: { status: vars.status },
        }),
        'set quest status',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

export function useToggleObjective(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { questId: string; index: number; done: boolean }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/quests/{quest_id}/objectives', {
          params: { path: { campaign_id: campaignId, quest_id: vars.questId } },
          body: { index: vars.index, done: vars.done },
        }),
        'toggle objective',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

export function useSetQuestDeadline(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { questId: string; deadline: number | null }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/quests/{quest_id}', {
          params: { path: { campaign_id: campaignId, quest_id: vars.questId } },
          body: { deadline_game: vars.deadline },
        }),
        'set deadline',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

export function useAddQuestDependency(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { questId: string; dependsOnId: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/quests/{quest_id}/dependencies', {
          params: { path: { campaign_id: campaignId, quest_id: vars.questId } },
          body: { depends_on_id: vars.dependsOnId },
        }),
        'add dependency',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

export function useRemoveQuestDependency(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { questId: string; dependsOnId: string }) =>
      unwrap(
        await api.DELETE(
          '/api/v1/campaigns/{campaign_id}/quests/{quest_id}/dependencies/{depends_on_id}',
          {
            params: {
              path: {
                campaign_id: campaignId,
                quest_id: vars.questId,
                depends_on_id: vars.dependsOnId,
              },
            },
          },
        ),
        'remove dependency',
      ),
    onSuccess: () => invalidateQuests(qc, campaignId),
  })
}

// --- NPC dynamics (FR-6) ----------------------------------------------------
export interface NpcFilters {
  status?: string
  location_id?: string
  faction_id?: string
  met_party?: boolean
  knows?: string
}

export function useNpcs(campaignId: string | null, filters: NpcFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['npcs', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/npcs', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load npcs',
      ),
  })
}

export function useNpcHistory(campaignId: string | null, npcId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!npcId,
    queryKey: ['npc-history', campaignId, npcId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/history', {
          params: { path: { campaign_id: campaignId!, npc_id: npcId! } },
        }),
        'load npc history',
      ),
  })
}

export function useNpcSchedules(campaignId: string | null, npcId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!npcId,
    queryKey: ['npc-schedules', campaignId, npcId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/schedules', {
          params: { path: { campaign_id: campaignId!, npc_id: npcId! } },
        }),
        'load npc schedules',
      ),
  })
}

/** "Where was X …" — an instant, a session span, or (with neither) right now. */
export async function whereWas(
  campaignId: string,
  npcId: string,
  query: { at_game?: number; session_id?: string } = {},
) {
  return unwrap(
    await api.GET('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/where', {
      params: { path: { campaign_id: campaignId, npc_id: npcId }, query },
    }),
    'locate npc',
  )
}

// An NPC write moves the graph, the timeline and the dashboard's NPCs-here panel.
function invalidateNpcs(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['npcs', campaignId] })
  void qc.invalidateQueries({ queryKey: ['npc-history', campaignId] })
  void qc.invalidateQueries({ queryKey: ['npc-schedules', campaignId] })
  void qc.invalidateQueries({ queryKey: ['entity', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
  void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
}

export function useCreateNpc(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { name: string; status?: string; location_id?: string | null }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/npcs', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create npc',
      ),
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

export function useRelocateNpc(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { npcId: string; locationId: string | null; reason?: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/relocate', {
          params: { path: { campaign_id: campaignId, npc_id: vars.npcId } },
          body: { location_id: vars.locationId, reason: vars.reason ?? null },
        }),
        'relocate npc',
      ),
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

export function useSetNpcStatus(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { npcId: string; status: string; reason?: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/status', {
          params: { path: { campaign_id: campaignId, npc_id: vars.npcId } },
          body: { status: vars.status, reason: vars.reason ?? null },
        }),
        'set npc status',
      ),
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

export function useRecordInteraction(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { npcId: string; summary?: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/interactions', {
          params: { path: { campaign_id: campaignId, npc_id: vars.npcId } },
          body: { summary: vars.summary ?? null },
        }),
        'record interaction',
      ),
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

export function useCreateNpcSchedule(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      npcId: string
      label: string
      interval_days: number
      stops: { at_seconds: number; location_id: string }[]
    }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}/schedules', {
          params: { path: { campaign_id: campaignId, npc_id: vars.npcId } },
          body: { label: vars.label, interval_days: vars.interval_days, stops: vars.stops },
        }),
        'create schedule',
      ),
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

export function useDeleteNpcSchedule(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (scheduleId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/npcs/schedules/{schedule_id}',
        { params: { path: { campaign_id: campaignId, schedule_id: scheduleId } } },
      )
      if (error) throw new Error('delete schedule')
    },
    onSuccess: () => invalidateNpcs(qc, campaignId),
  })
}

// --- travel (FR-5.3) --------------------------------------------------------
export interface TravelLegInput {
  distance: number
  terrain?: string
  pace?: string
  conveyance?: string
  to_location_id?: string | null
}

export function useTravelTable(systemId: string | null) {
  return useQuery({
    enabled: !!systemId,
    queryKey: ['travel-table', systemId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/rule-systems/{system_id}/travel', {
          params: { path: { system_id: systemId! } },
        }),
        'load travel table',
      ),
  })
}

export async function previewTravel(
  campaignId: string,
  legs: TravelLegInput[],
  forced_march: boolean,
) {
  const { data, error } = await api.POST('/api/v1/campaigns/{campaign_id}/party/travel/preview', {
    params: { path: { campaign_id: campaignId } },
    body: { legs, forced_march },
  })
  if (error || !data) {
    const detail = (error as { detail?: unknown } | undefined)?.detail
    throw new Error(typeof detail === 'string' ? detail : 'preview travel')
  }
  return data
}

export function useCommitTravel(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { legs: TravelLegInput[]; forced_march: boolean }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/party/travel', {
          params: { path: { campaign_id: campaignId } },
          body: vars,
        }),
        'travel',
      ),
    onSuccess: () => {
      invalidateParty(qc, campaignId)
      invalidateNpcs(qc, campaignId)
      void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] })
    },
  })
}

// --- data lifecycle (FR-13): references, article history, backups -----------
/** Delete-preflight: what points at this entity. Imperative — fetched on demand. */
export async function fetchReferences(campaignId: string, entityId: string) {
  return unwrap(
    await api.GET('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/references', {
      params: { path: { campaign_id: campaignId, entity_id: entityId } },
    }),
    'load references',
  )
}

export function useArticleSnapshots(campaignId: string | null, entityId: string, enabled: boolean) {
  return useQuery({
    enabled: !!campaignId && enabled,
    queryKey: ['article-snapshots', campaignId, entityId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/article/snapshots', {
          params: { path: { campaign_id: campaignId!, entity_id: entityId } },
        }),
        'load article history',
      ),
  })
}

export function useRestoreArticleSnapshot(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (snapshotId: string) =>
      unwrap(
        await api.POST(
          '/api/v1/campaigns/{campaign_id}/entities/{entity_id}/article/snapshots/{snapshot_id}/restore',
          {
            params: {
              path: { campaign_id: campaignId, entity_id: entityId, snapshot_id: snapshotId },
            },
          },
        ),
        'restore article',
      ),
    onSuccess: () => {
      invalidateCampaign(qc, campaignId)
      void qc.invalidateQueries({ queryKey: ['article-snapshots', campaignId, entityId] })
    },
  })
}

export function useBackups() {
  return useQuery({
    queryKey: ['backups'],
    queryFn: async () => unwrap(await api.GET('/api/v1/backups'), 'load backups'),
  })
}

export function useCreateBackup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (reason: string) =>
      unwrap(await api.POST('/api/v1/backups', { body: { reason } }), 'create backup'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['backups'] }),
  })
}

// --- events -----------------------------------------------------------------
export function useEvents(campaignId: string | null, limit = 20) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['events', campaignId, limit],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/events', {
          params: { path: { campaign_id: campaignId! }, query: { limit } },
        }),
        'load events',
      ),
  })
}
