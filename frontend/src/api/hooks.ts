// TanStack Query hooks over the typed client. Mutations invalidate the affected
// queries so views stay fresh without manual refetching (FR-14.3).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { applyOptimistic } from '../lib/combatReducer'
import type { CombatState } from '../lib/combatReducer'
import { api } from './client'
import type {
  CampaignCreate,
  EntityCreate,
  EntityUpdate,
  StoryEdgeIn,
  StoryGraph,
  StoryNodeIn,
  StoryNodeUpdate,
} from './client'
import type { components } from './schema'

type SkillChallengeCreate = components['schemas']['SkillChallengeCreate']
type SkillChallengeUpdate = components['schemas']['SkillChallengeUpdate']
type RecordCheckIn = components['schemas']['RecordCheckIn']

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
  q?: string
  sort?: string
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

export type DeepSearchFilters = {
  entity_type?: string
  tag_id?: string
  prose_only?: boolean
  limit?: number
}

// Ranked search that returns highlighted snippets of the summary/article prose that
// matched — the Search page. Disabled on a blank query so it doesn't fetch on mount.
export function useDeepSearch(
  campaignId: string | null,
  q: string,
  filters: DeepSearchFilters = {},
) {
  return useQuery({
    enabled: !!campaignId && q.trim().length > 0,
    queryKey: ['deep-search', campaignId, q, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/search/deep', {
          params: { path: { campaign_id: campaignId! }, query: { q, ...filters } },
        }),
        'search',
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

/** Permanently destroy every soft-deleted entity in the campaign. Irreversible. */
export function usePurgeDeletedEntities(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/entities/purge', {
          params: { path: { campaign_id: campaignId } },
        }),
        'purge deleted entities',
      ),
    onSuccess: () => invalidateCampaign(qc, campaignId),
  })
}

// --- tags -------------------------------------------------------------------
export function useTags(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['tags', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/tags', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load tags',
      ),
  })
}

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

// Monster name search for the palette — monsters aren't wiki entities, so they don't ride
// the entity FTS index; the bestiary endpoint does its own name match (unbounded, so cap here).
export async function searchMonsters(campaignId: string, q: string, limit = 8) {
  const { data } = await api.GET('/api/v1/campaigns/{campaign_id}/monsters', {
    params: { path: { campaign_id: campaignId }, query: { q } },
  })
  return (data ?? []).slice(0, limit)
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

export function useSetClock(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: { time_game: number; set_as_start?: boolean; reason?: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/clock/set', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'set clock',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
      void qc.invalidateQueries({ queryKey: ['events', campaignId] })
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
      description?: string | null
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

export function useUpdateScheduledEvent(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      eventId: string
      title?: string
      fire_at_game?: number
      action_type?: string
      action_json?: Record<string, unknown>
      recurrence_days?: number | null
      description?: string | null
    }) => {
      const { eventId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/scheduled-events/{event_id}', {
          params: { path: { campaign_id: campaignId, event_id: eventId } },
          body,
        }),
        'update scheduled event',
      )
    },
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

// A single stat block by id — used by the combat tracker to show the selected combatant.
export function useStatBlock(campaignId: string | null, blockId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!blockId,
    queryKey: ['stat-block', campaignId, blockId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/stat-blocks/{block_id}', {
          params: { path: { campaign_id: campaignId!, block_id: blockId! } },
        }),
        'load stat block',
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
    mutationFn: async (body: components['schemas']['PartyPatch']) =>
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

export function useConnections(campaignId: string | null) {
  return useQuery({
    queryKey: ['connections', campaignId],
    queryFn: async () => {
      if (!campaignId) return []
      return unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/party/connections', {
          params: { path: { campaign_id: campaignId } },
        }),
        'load connections',
      )
    },
    enabled: !!campaignId,
  })
}

export function useCreateConnection(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['LocationConnectionCreate']) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/party/connections', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create connection',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['connections', campaignId] })
    },
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

/**
 * Spend one of a party member's spell slots out of combat, or hand one back (`delta: 1`).
 *
 * In a fight casting rides the combat fold, where Undo already puts the slot back; this is
 * the other half — the wizard who casts *identify* over breakfast.
 */
export function useCastPartySpell(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { statBlockId: string; poolKey: string; delta?: number }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/party/members/{stat_block_id}/cast', {
          params: {
            path: { campaign_id: campaignId, stat_block_id: vars.statBlockId },
          },
          body: { pool_key: vars.poolKey, delta: vars.delta ?? -1 },
        }),
        'cast spell',
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
// Types come straight from the generated OpenAPI schema — the folded combat state is the
// reducer's own shape (see lib/combatReducer.ts, its TS twin), so a backend contract change
// surfaces here as a type error rather than at the table.

export type CombatRun = components['schemas']['CombatRunOut']
export type CombatStateOut = components['schemas']['CombatState']
export type CombatantOut = components['schemas']['Combatant']
export type CombatSummary = components['schemas']['CombatSummary']
export type ConditionDef = components['schemas']['ConditionOut']
export type CombatRoll = components['schemas']['CombatRollOut']
export type RollInitiativeIn = components['schemas']['RollInitiativeIn']
export type AddCombatantIn = components['schemas']['AddCombatantIn']
export type DeathSaveRules = components['schemas']['DeathSaveRulesOut']
export type Attack = components['schemas']['AttackOut']
export type AttackIn = components['schemas']['AttackIn']
export type AttackResult = components['schemas']['AttackResultOut']
export type SpellAction = components['schemas']['SpellActionOut']
/** A party member's pool as the sheet sees it — carries its own key (combat keys by dict). */
export type SpellPoolOut = components['schemas']['SpellPoolOut']

// The reducer's action vocabulary, pinned to a Literal by the backend. A typo is a compile
// error here rather than a 422 mid-combat.
export type CombatActionType = components['schemas']['CombatActionIn']['action_type']

const combatKey = (campaignId: string | null, runId: string | null) =>
  ['combat', campaignId, runId] as const

// A combat write moves more than the tracker: the clock (6s per round), the dashboard's
// active-combat panel, and — once a run ends — the timeline and the party's HP, since
// end_combat writes each PC's folded HP back to their sheet.
function invalidateCombat(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
  void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
  // Starting, ending, or cancelling all change which runs are still in play.
  void qc.invalidateQueries({ queryKey: ['combats', 'open', campaignId] })
  void qc.invalidateQueries({ queryKey: ['party', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
}

/**
 * The campaign's in-play runs (setup or active), newest first.
 *
 * This is how the tracker finds a fight it has no local pointer to. localStorage alone was
 * never enough: clear it, or open the app in another browser, and a running combat became
 * unreachable while the dashboard went on forcing the combat preset.
 */
export function useOpenCombats(campaignId: string | null, enabled = true) {
  return useQuery({
    enabled: !!campaignId && enabled,
    queryKey: ['combats', 'open', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/combats', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load open combats',
      ),
  })
}

export function useCombat(campaignId: string | null, runId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!runId,
    queryKey: combatKey(campaignId, runId),
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/combats/{run_id}', {
          params: { path: { campaign_id: campaignId!, run_id: runId! } },
        }),
        'load combat',
      ),
    // The fold is authoritative and only this client writes to it; refetching on focus
    // would stomp an optimistic action that is still in flight.
    refetchOnWindowFocus: false,
  })
}

/** Apply an action optimistically, then reconcile with the server's authoritative fold. */
export function useCombatAction(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  const key = combatKey(campaignId, runId)
  return useMutation({
    mutationFn: async (vars: { type: CombatActionType; payload: Record<string, unknown> }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/actions', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
          body: { action_type: vars.type, payload: vars.payload },
        }),
        'combat action',
      ),
    // Optimistic via the TS reducer twin so each action feels instant (NFR-1.3). Rolling
    // back on failure is the point: this used to leave the optimistic state on screen
    // permanently, so a rejected action showed the GM a wound the server never recorded.
    onMutate: async (vars) => {
      await qc.cancelQueries({ queryKey: key })
      const previous = qc.getQueryData<CombatRun>(key)
      if (previous) {
        qc.setQueryData<CombatRun>(key, {
          ...previous,
          state: applyOptimistic(previous.state as CombatState, {
            type: vars.type,
            ...vars.payload,
          }) as CombatRun['state'],
        })
      }
      return { previous }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(key, ctx.previous)
    },
    onSuccess: (run) => {
      qc.setQueryData(key, run)
      invalidateCombat(qc, campaignId)
    },
  })
}

/** Roll initiative for a scope and/or submit the totals the GM typed in — one round trip. */
export function useRollInitiative(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RollInitiativeIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/initiative', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
          body,
        }),
        'roll initiative',
      ),
    onSuccess: (run) => {
      qc.setQueryData(combatKey(campaignId, runId), run)
      void qc.invalidateQueries({ queryKey: ['combat-rolls', campaignId, runId] })
    },
  })
}

/** Add a straggler mid-fight. The server seeds it from the plugin and rolls it in. */
export function useAddCombatant(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: AddCombatantIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/combatants', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
          body,
        }),
        'add combatant',
      ),
    onSuccess: (run) => {
      qc.setQueryData(combatKey(campaignId, runId), run)
      void qc.invalidateQueries({ queryKey: ['combat-rolls', campaignId, runId] })
    },
  })
}

/** Roll one death save. Which die, against what, and what a 20 means are the plugin's. */
export function useRollDeathSave(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (args: string | { combatantId: string; manualResult: number }) => {
      const { combatantId, manualResult } =
        typeof args === 'string' ? { combatantId: args, manualResult: undefined } : args
      return unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/death-save', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
          body: { combatant_id: combatantId, manual_result: manualResult },
        }),
        'roll death save',
      )
    },
    onSuccess: (run) => {
      qc.setQueryData(combatKey(campaignId, runId), run)
      void qc.invalidateQueries({ queryKey: ['combat-rolls', campaignId, runId] })
    },
  })
}

/** Leave setup and start round 1. */
export function useBeginCombat(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/begin', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
        }),
        'begin combat',
      ),
    onSuccess: (run) => {
      qc.setQueryData(combatKey(campaignId, runId), run)
      invalidateCombat(qc, campaignId)
    },
  })
}

/** What this combatant can do, resolved by its rule system into plain numbers. */
export function useCombatantAttacks(
  campaignId: string | null,
  runId: string | null,
  combatantId: string | null,
) {
  return useQuery({
    enabled: !!campaignId && !!runId && !!combatantId,
    queryKey: ['combat-attacks', campaignId, runId, combatantId],
    queryFn: async () =>
      unwrap(
        await api.GET(
          '/api/v1/campaigns/{campaign_id}/combats/{run_id}/combatants/{combatant_id}/attacks',
          {
            params: {
              path: { campaign_id: campaignId!, run_id: runId!, combatant_id: combatantId! },
            },
          },
        ),
        'load attacks',
      ),
    // An attack only changes when someone edits the sheet behind it.
    staleTime: 5 * 60_000,
  })
}

/**
 * What this combatant can cast, and which pool each casting spends.
 *
 * Read-only: spending is an ordinary `cast_spell` action through `useCombatAction`, which
 * is what puts it in the fold and makes Undo give the slot back.
 */
export function useCombatantSpells(
  campaignId: string | null,
  runId: string | null,
  combatantId: string | null,
) {
  return useQuery({
    enabled: !!campaignId && !!runId && !!combatantId,
    queryKey: ['combat-spells', campaignId, runId, combatantId],
    queryFn: async () =>
      unwrap(
        await api.GET(
          '/api/v1/campaigns/{campaign_id}/combats/{run_id}/combatants/{combatant_id}/spells',
          {
            params: {
              path: { campaign_id: campaignId!, run_id: runId!, combatant_id: combatantId! },
            },
          },
        ),
        'load spells',
      ),
    // Like attacks: the list only changes when someone edits the sheet behind it. What's
    // *left* of each pool lives in the fold, not here.
    staleTime: 5 * 60_000,
  })
}

/**
 * Roll an attack. Deliberately does not touch combat state — the result is a report, and
 * applying it is a separate `damage` action the GM chooses to fire.
 */
export function useRollAttack(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: AttackIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/attack', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
          body,
        }),
        'roll attack',
      ),
    // Only the roll log moved; the fold is untouched, so the combat query stays as it was.
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['combat-rolls', campaignId, runId] }),
  })
}

/** The run's roll log. Append-only and outside the fold, so undo never erases it. */
export function useCombatRolls(campaignId: string | null, runId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!runId,
    queryKey: ['combat-rolls', campaignId, runId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/combats/{run_id}/rolls', {
          params: { path: { campaign_id: campaignId!, run_id: runId! } },
        }),
        'load rolls',
      ),
  })
}

/** Undo and redo move the fold cursor; both skip the optimistic step and take the server's word. */
function useCursorMove(campaignId: string, runId: string | null, dir: 'undo' | 'redo') {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST(`/api/v1/campaigns/{campaign_id}/combats/{run_id}/${dir}` as const, {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
        }),
        dir,
      ),
    onSuccess: (run) => {
      qc.setQueryData(combatKey(campaignId, runId), run)
      invalidateCombat(qc, campaignId)
    },
  })
}

export const useCombatUndo = (campaignId: string, runId: string | null) =>
  useCursorMove(campaignId, runId, 'undo')
export const useCombatRedo = (campaignId: string, runId: string | null) =>
  useCursorMove(campaignId, runId, 'redo')

export function useEndCombat(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats/{run_id}/end', {
          params: { path: { campaign_id: campaignId, run_id: runId! } },
        }),
        'end combat',
      ),
    onSuccess: () => {
      // The run's status flipped to completed and PC HP was written back to the party.
      void qc.invalidateQueries({ queryKey: combatKey(campaignId, runId) })
      invalidateCombat(qc, campaignId)
    },
  })
}

/**
 * Call the fight off. Unlike ending it there is no summary and nothing is written back —
 * the run closes, the clock rewinds to where it started, and the campaign leaves combat
 * mode. Invalidating the dashboard is the part that matters: `active_combat` is what pins
 * it to the combat preset.
 */
export function useCancelCombat(campaignId: string, runId: string | null) {
  const qc = useQueryClient()
  return useMutation({
    // 204, so there is no body to unwrap — only an error worth raising.
    mutationFn: async () => {
      const { error } = await api.POST(
        '/api/v1/campaigns/{campaign_id}/combats/{run_id}/cancel',
        { params: { path: { campaign_id: campaignId, run_id: runId! } } },
      )
      if (error) throw new Error('cancel combat')
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: combatKey(campaignId, runId) })
      invalidateCombat(qc, campaignId)
    },
  })
}

/** The rule system's own condition list — 5e ships 15, Nimble a different 10. */
export function useConditions(systemId: string | null) {
  return useQuery({
    enabled: !!systemId,
    queryKey: ['conditions', systemId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/rule-systems/{system_id}/conditions', {
          params: { path: { system_id: systemId! } },
        }),
        'load conditions',
      ),
    // A rule system's conditions cannot change without a redeploy.
    staleTime: Infinity,
  })
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

// One roster line: a bestiary monster or a campaign NPC, never both.
interface CombatantSpec {
  monster_id?: string | null
  //: Fallback identity, so a bestiary re-import that renumbers monster IDs degrades to a
  //: resolvable name instead of "(missing)". Send it whenever it is known.
  monster_name?: string | null
  npc_id?: string | null
  npc_name?: string | null
  count: number
  side?: string
}

export interface EnvironmentActionSpec {
  name: string
  description?: string
}

export interface EnvironmentSpec {
  name: string
  initiative?: number | null
  actions?: EnvironmentActionSpec[]
}

export function useCreateEncounter(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      name: string
      terrain?: string | null
      hazards?: string | null
      tactics?: string | null
      combatants: CombatantSpec[]
      environment?: EnvironmentSpec[]
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

// Edits the structured half of an encounter (terrain/hazards/tactics/roster). Its name,
// summary and location link live on the underlying entity — those go through
// `useUpdateEntity`, so this deliberately has no `name` field.
export function useUpdateEncounter(campaignId: string, encounterId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      terrain?: string | null
      hazards?: string | null
      tactics?: string | null
      combatants?: CombatantSpec[]
      environment?: EnvironmentSpec[]
    }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/encounters/{encounter_id}', {
          params: { path: { campaign_id: campaignId, encounter_id: encounterId } },
          body,
        }),
        'update encounter',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['encounter', campaignId, encounterId] })
      void qc.invalidateQueries({ queryKey: ['encounters', campaignId] })
    },
  })
}

export function useEncounter(campaignId: string | null, encounterId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!encounterId,
    queryKey: ['encounter', campaignId, encounterId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/encounters/{encounter_id}', {
          params: { path: { campaign_id: campaignId!, encounter_id: encounterId! } },
        }),
        'load encounter',
      ),
  })
}

// Combat runs started from a given encounter (for the encounter page's "combat" section).
export function useEncounterCombats(campaignId: string | null, encounterId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!encounterId,
    queryKey: ['encounter-combats', campaignId, encounterId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/combats', {
          params: { path: { campaign_id: campaignId! }, query: { encounter_id: encounterId! } },
        }),
        'load encounter combats',
      ),
  })
}

// Shared by the encounter panel's "start combat" and the combat page's own picker, so the
// run is cached either way — arriving at /combat from an encounter shouldn't refetch a run
// the server just handed us.
export function useStartCombat(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (encounterId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/combats', {
          params: { path: { campaign_id: campaignId } },
          body: { encounter_id: encounterId },
        }),
        'start combat',
      ),
    onSuccess: (run, encounterId) => {
      qc.setQueryData(combatKey(campaignId, run.run_id), run)
      void qc.invalidateQueries({ queryKey: ['encounter-combats', campaignId, encounterId] })
      invalidateCombat(qc, campaignId)
    },
  })
}

// --- bestiary ---------------------------------------------------------------
interface MonsterFilters {
  q?: string
  facet1_num_gte?: number
  facet1_num_lte?: number
  facet1_text?: string
  //: The server caps the list (default 200) and has no offset — raising this is how a
  //: picker reaches past the cap in a campaign with a large bestiary.
  limit?: number
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

export function useCreateMonster(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (name: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/monsters', {
          params: { path: { campaign_id: campaignId } },
          body: { name },
        }),
        'create monster',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['monsters', campaignId] }),
  })
}

export function useDeleteMonster(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (monsterId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/monsters/{monster_id}',
        { params: { path: { campaign_id: campaignId, monster_id: monsterId } } },
      )
      if (error) throw new Error('delete monster')
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['monsters', campaignId] }),
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

// Hide/unhide a single entry (projected or lore). The "Show hidden" filter reveals hidden ones.
export function useSetTimelineHidden(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { entryId: string; hidden: boolean }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/timeline/{entry_id}', {
          params: { path: { campaign_id: campaignId, entry_id: vars.entryId } },
          body: { is_hidden: vars.hidden },
        }),
        'update timeline entry',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['timeline', campaignId] }),
  })
}

// Delete a single manual lore entry (projected entries can only be hidden, not deleted).
export function useDeleteTimelineEntry(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (entryId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/timeline/{entry_id}',
        { params: { path: { campaign_id: campaignId, entry_id: entryId } } },
      )
      if (error) throw new Error('delete timeline entry')
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['timeline', campaignId] }),
  })
}

// Wipes the whole timeline and resets the clock back to the campaign's start time.
export function useClearTimeline(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/timeline/clear', {
          params: { path: { campaign_id: campaignId } },
        }),
        'clear timeline',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
      void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
      void qc.invalidateQueries({ queryKey: ['events', campaignId] })
      void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
    },
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

export function useDeleteSession(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    // 204, so there is no body to unwrap — `unwrap` would read the empty response as a
    // failure and skip the invalidation, leaving a deleted session on screen.
    mutationFn: async (sessionId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/sessions/{session_id}',
        { params: { path: { campaign_id: campaignId, session_id: sessionId } } },
      )
      if (error) {
        const detail = (error as { detail?: unknown }).detail
        throw new Error(typeof detail === 'string' ? detail : 'delete session')
      }
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
      description?: string | null
      locationId?: string | null
      parentMapId?: string | null
    }) => {
      const fd = new FormData()
      fd.append('file', vars.file)
      fd.append('name', vars.name)
      fd.append('map_kind', vars.mapKind)
      if (vars.description) fd.append('description', vars.description)
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

export function useUpdateMap(campaignId: string, mapId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['MapUpdate']) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/maps/{map_id}', {
          params: { path: { campaign_id: campaignId, map_id: mapId } },
          body,
        }),
        'update map',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['maps', campaignId] })
      void qc.invalidateQueries({ queryKey: ['map', campaignId, mapId] })
    },
  })
}

// Attach/detach a map to a location from anywhere (the map id is a variable, not a hook
// key, so one instance can retarget any map — e.g. the location page's picker).
// NOTE: the backend treats `location_id: null` as "not provided" (no-op); the clear
// sentinel is the empty string (service.update_map: `m.location_id = location_id or None`).
export function useSetMapLocation(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { mapId: string; locationId: string | '' }) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/maps/{map_id}', {
          params: { path: { campaign_id: campaignId, map_id: vars.mapId } },
          body: { location_id: vars.locationId },
        }),
        'update map location',
      ),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({ queryKey: ['maps', campaignId] })
      void qc.invalidateQueries({ queryKey: ['map', campaignId, vars.mapId] })
    },
  })
}

// --- entity image attachments ----------------------------------------------
export function useEntityMedia(campaignId: string | null, entityId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!entityId,
    queryKey: ['entity-media', campaignId, entityId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/entities/{entity_id}/media', {
          params: { path: { campaign_id: campaignId!, entity_id: entityId! } },
        }),
        'load entity images',
      ),
  })
}

// Multipart upload bypasses the JSON client (same pattern as useUploadMap).
export function useUploadEntityMedia(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { file: File; caption?: string }) => {
      const fd = new FormData()
      fd.append('file', vars.file)
      if (vars.caption) fd.append('caption', vars.caption)
      const res = await fetch(
        `/api/v1/campaigns/${campaignId}/entities/${entityId}/media`,
        { method: 'POST', body: fd },
      )
      if (!res.ok) {
        const detail = (await res.json().catch(() => ({})))?.detail
        throw new Error(typeof detail === 'string' ? detail : 'upload image')
      }
      return (await res.json()) as import('./client').AttachmentOut
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['entity-media', campaignId, entityId] }),
  })
}

export function useDeleteEntityMedia(campaignId: string, entityId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (attachmentId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/entities/{entity_id}/media/{attachment_id}',
        {
          params: {
            path: { campaign_id: campaignId, entity_id: entityId, attachment_id: attachmentId },
          },
        },
      )
      if (error) throw new Error('delete image')
    },
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: ['entity-media', campaignId, entityId] }),
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
  include_deleted?: boolean
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

export function useNpc(campaignId: string | null, npcId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!npcId,
    queryKey: ['npc', campaignId, npcId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}', {
          params: { path: { campaign_id: campaignId!, npc_id: npcId! } },
        }),
        'load npc',
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
  void qc.invalidateQueries({ queryKey: ['npc', campaignId] })
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

// GM notes (goals / secrets / voice_notes) and the NPC's combat sheet link.
// Backend PATCH /npcs/{npc_id}.
export function useUpdateNpc(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: {
      npcId: string
      goals?: string | null
      secrets?: string | null
      voice_notes?: string | null
      stat_block_id?: string | null
    }) => {
      const { npcId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/npcs/{npc_id}', {
          params: { path: { campaign_id: campaignId, npc_id: npcId } },
          body,
        }),
        'update npc',
      )
    },
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
  travel_type?: string
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

// --- random tables (FR-12) -------------------------------------------------
type RandomTableCreate = components['schemas']['RandomTableCreate']
type RandomTableUpdate = components['schemas']['RandomTableUpdate']

export function useRandomTables(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['random-tables', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/random-tables', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load random tables',
      ),
  })
}

export function useRandomTable(campaignId: string | null, tableId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!tableId,
    queryKey: ['random-table', campaignId, tableId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/random-tables/{table_id}', {
          params: { path: { campaign_id: campaignId!, table_id: tableId! } },
        }),
        'load random table',
      ),
  })
}

export function useCreateRandomTable(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RandomTableCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/random-tables', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create random table',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['random-tables', campaignId] })
      void qc.invalidateQueries({ queryKey: ['entity', campaignId] })
    },
  })
}

export function useUpdateRandomTable(campaignId: string, tableId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RandomTableUpdate) =>
      unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/random-tables/{table_id}', {
          params: { path: { campaign_id: campaignId, table_id: tableId } },
          body,
        }),
        'update random table',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['random-tables', campaignId] })
      void qc.invalidateQueries({ queryKey: ['random-table', campaignId, tableId] })
    },
  })
}

export function useDeleteRandomTable(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (tableId: string) => {
      const { error } = await api.DELETE(
        '/api/v1/campaigns/{campaign_id}/random-tables/{table_id}',
        { params: { path: { campaign_id: campaignId, table_id: tableId } } },
      )
      if (error) throw new Error('delete random table')
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['random-tables', campaignId] })
      void qc.invalidateQueries({ queryKey: ['entities', campaignId] })
    },
  })
}

// Rolling is a non-idempotent read (POST) — it mutates nothing, so it invalidates nothing.
export async function rollTable(campaignId: string, tableId: string) {
  return unwrap(
    await api.POST('/api/v1/campaigns/{campaign_id}/random-tables/{table_id}/roll', {
      params: { path: { campaign_id: campaignId, table_id: tableId } },
    }),
    'roll table',
  )
}

// --- skill challenges (FR-12) ----------------------------------------------
export function useSkillChallenges(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['skill-challenges', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/skill-challenges', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load skill challenges',
      ),
  })
}

// A skill challenge's id *is* its wiki entity id, so this doubles as "the challenge
// for this entity".
export function useSkillChallenge(campaignId: string | null, challengeId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!challengeId,
    queryKey: ['skill-challenge', campaignId, challengeId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/skill-challenges/{challenge_id}', {
          params: { path: { campaign_id: campaignId!, challenge_id: challengeId! } },
        }),
        'load skill challenge',
      ),
  })
}

export function useUpdateSkillChallenge(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { challengeId: string } & SkillChallengeUpdate) => {
      const { challengeId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/skill-challenges/{challenge_id}', {
          params: { path: { campaign_id: campaignId, challenge_id: challengeId } },
          body,
        }),
        'update skill challenge',
      )
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['skill-challenges', campaignId] })
      void qc.invalidateQueries({ queryKey: ['skill-challenge', campaignId] })
    },
  })
}

export function useCreateSkillChallenge(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SkillChallengeCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/skill-challenges', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create skill challenge',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['skill-challenges', campaignId] })
      void qc.invalidateQueries({ queryKey: ['entity', campaignId] })
    },
  })
}

export function useSkillRun(campaignId: string | null, runId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!runId,
    queryKey: ['skill-run', campaignId, runId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/skill-runs/{run_id}', {
          params: { path: { campaign_id: campaignId!, run_id: runId! } },
        }),
        'load skill run',
      ),
  })
}

export function useStartSkillRun(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (challengeId: string | null) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/skill-runs', {
          params: { path: { campaign_id: campaignId } },
          body: { challenge_id: challengeId },
        }),
        'start skill run',
      ),
    onSuccess: (run) =>
      void qc.setQueryData(['skill-run', campaignId, run.run_id], run),
  })
}

export function useRecordSkillCheck(campaignId: string, runId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: RecordCheckIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/skill-runs/{run_id}/checks', {
          params: { path: { campaign_id: campaignId, run_id: runId } },
          body,
        }),
        'record check',
      ),
    onSuccess: (run) =>
      void qc.setQueryData(['skill-run', campaignId, runId], run),
  })
}

export function useSkillRunAction(
  campaignId: string,
  runId: string,
  action: 'undo' | 'resolve',
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST(
          `/api/v1/campaigns/{campaign_id}/skill-runs/{run_id}/${action}` as
            '/api/v1/campaigns/{campaign_id}/skill-runs/{run_id}/undo',
          { params: { path: { campaign_id: campaignId, run_id: runId } } },
        ),
        action === 'undo' ? 'undo check' : 'resolve run',
      ),
    onSuccess: (run) =>
      void qc.setQueryData(['skill-run', campaignId, runId], run),
  })
}

export function useRollWeather(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/weather/roll', {
          params: { path: { campaign_id: campaignId } },
        }),
        'roll weather',
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['scheduled-events', campaignId] })
      void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
      void qc.invalidateQueries({ queryKey: ['flags', campaignId] })
      void qc.invalidateQueries({ queryKey: ['events', campaignId] })
      void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
    },
  })
}

// --- equipment: catalog (definitions) + items (copies) ----------------------
// Two tiers mirror the backend: `Equipment` is a reusable definition, `Item` is
// a physical copy of one. Types come straight from the generated OpenAPI schema.

export type Equipment = components['schemas']['EquipmentOut']
export type EquipmentCreate = components['schemas']['EquipmentCreate']
export type EquipmentUpdate = components['schemas']['EquipmentUpdate']
export type Item = components['schemas']['ItemInstanceOut']
export type ItemInstanceCreate = components['schemas']['ItemInstanceCreate']
export type ItemInstanceUpdate = components['schemas']['ItemInstanceUpdate']
export type TransferIn = components['schemas']['TransferIn']
export type OwnershipRow = components['schemas']['OwnershipRow']

export interface EquipmentFilters {
  item_type?: string
  rarity?: string
}

export interface ItemFilters {
  equipment_id?: string
  holder_type?: string
  holder_id?: string
  location_id?: string
}

function invalidateEquipment(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['equipment', campaignId] })
  void qc.invalidateQueries({ queryKey: ['items', campaignId] })
  void qc.invalidateQueries({ queryKey: ['item-history', campaignId] })
  void qc.invalidateQueries({ queryKey: ['entities', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
}

// -- catalog ------------------------------------------------------------------

export function useEquipmentList(campaignId: string | null, filters: EquipmentFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['equipment', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/equipment', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load equipment',
      ),
  })
}

export function useEquipment(campaignId: string | null, equipId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!equipId,
    queryKey: ['equipment', campaignId, 'one', equipId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/equipment/{equip_id}', {
          params: { path: { campaign_id: campaignId!, equip_id: equipId! } },
        }),
        'load equipment',
      ),
  })
}

export function useCreateEquipment(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: EquipmentCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/equipment', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create equipment',
      ),
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useUpdateEquipment(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { equipId: string } & EquipmentUpdate) => {
      const { equipId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/equipment/{equip_id}', {
          params: { path: { campaign_id: campaignId, equip_id: equipId } },
          body,
        }),
        'update equipment',
      )
    },
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useDeleteEquipment(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (equipId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/equipment/{equip_id}', {
          params: { path: { campaign_id: campaignId, equip_id: equipId } },
        }),
        'delete equipment',
      ),
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

// -- item instances -----------------------------------------------------------

export function useItems(campaignId: string | null, filters: ItemFilters = {}) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['items', campaignId, filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/items', {
          params: { path: { campaign_id: campaignId! }, query: filters },
        }),
        'load items',
      ),
  })
}

export function useItem(campaignId: string | null, itemId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!itemId,
    queryKey: ['items', campaignId, 'one', itemId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/items/{item_id}', {
          params: { path: { campaign_id: campaignId!, item_id: itemId! } },
        }),
        'load item',
      ),
  })
}

export function useItemHistory(campaignId: string | null, itemId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!itemId,
    queryKey: ['item-history', campaignId, itemId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/items/{item_id}/history', {
          params: { path: { campaign_id: campaignId!, item_id: itemId! } },
        }),
        'load item history',
      ),
  })
}

export function useCreateItem(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: ItemInstanceCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/items', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create item',
      ),
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useUpdateItem(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { itemId: string } & ItemInstanceUpdate) => {
      const { itemId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/items/{item_id}', {
          params: { path: { campaign_id: campaignId, item_id: itemId } },
          body,
        }),
        'update item',
      )
    },
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useTransferItem(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { itemId: string } & TransferIn) => {
      const { itemId, ...body } = vars
      return unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/items/{item_id}/transfer', {
          params: { path: { campaign_id: campaignId, item_id: itemId } },
          body,
        }),
        'transfer item',
      )
    },
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useDeleteItem(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (itemId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/items/{item_id}', {
          params: { path: { campaign_id: campaignId, item_id: itemId } },
        }),
        'delete item',
      ),
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

// --- equipment library (global, campaign-independent templates) --------------

export type LibraryEntry = components['schemas']['LibraryEntryOut']
export type LibraryEntryCreate = components['schemas']['LibraryEntryCreate']
export type LibraryEntryUpdate = components['schemas']['LibraryEntryUpdate']

export interface LibraryFilters {
  item_type?: string
  rarity?: string
  q?: string
}

export function useEquipmentLibrary(filters: LibraryFilters = {}) {
  return useQuery({
    queryKey: ['equipment-library', filters],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/equipment-library', { params: { query: filters } }),
        'load equipment library',
      ),
  })
}

export function useCreateLibraryEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: LibraryEntryCreate) =>
      unwrap(await api.POST('/api/v1/equipment-library', { body }), 'create library entry'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['equipment-library'] }),
  })
}

export function useUpdateLibraryEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { entryId: string } & LibraryEntryUpdate) => {
      const { entryId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/equipment-library/{entry_id}', {
          params: { path: { entry_id: entryId } },
          body,
        }),
        'update library entry',
      )
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['equipment-library'] }),
  })
}

export function useDeleteLibraryEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (entryId: string) =>
      unwrap(
        await api.DELETE('/api/v1/equipment-library/{entry_id}', {
          params: { path: { entry_id: entryId } },
        }),
        'delete library entry',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['equipment-library'] }),
  })
}

export function useImportFromLibrary(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (libraryId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/equipment/import', {
          params: { path: { campaign_id: campaignId } },
          body: { library_id: libraryId },
        }),
        'import from library',
      ),
    onSuccess: () => invalidateEquipment(qc, campaignId),
  })
}

export function useSaveToLibrary(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (equipId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/equipment/{equip_id}/save-to-library', {
          params: { path: { campaign_id: campaignId, equip_id: equipId } },
        }),
        'save to library',
      ),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['equipment-library'] }),
  })
}

// --- spells (global, campaign-independent reference) -------------------------

export type Spell = components['schemas']['SpellOut']
export type SpellCreate = components['schemas']['SpellCreate']

export interface SpellFilters {
  level?: number
  school?: string
  class?: string
  source?: string
  q?: string
}

export function useSpells(filters: SpellFilters = {}) {
  return useQuery({
    queryKey: ['spells', filters],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/spells', { params: { query: filters } }), 'load spells'),
  })
}

/** Filter options present in the catalog — avoids pulling all ~900 spells to fill dropdowns. */
export function useSpellFacets() {
  return useQuery({
    queryKey: ['spell-facets'],
    queryFn: async () =>
      unwrap(await api.GET('/api/v1/spells/facets', {}), 'load spell facets'),
  })
}

export function useCreateSpell() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: SpellCreate) =>
      unwrap(await api.POST('/api/v1/spells', { body }), 'create spell'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['spells'] }),
  })
}

// --- merchants (shops) -------------------------------------------------------

export type Merchant = components['schemas']['MerchantOut']
export type MerchantCreate = components['schemas']['MerchantCreate']
export type MerchantUpdate = components['schemas']['MerchantUpdate']
export type StockLine = components['schemas']['StockLineOut']
export type PurchaseResult = components['schemas']['PurchaseResult']
export type SellbackResult = components['schemas']['SellbackResult']

function invalidateMerchants(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['merchants', campaignId] })
  void qc.invalidateQueries({ queryKey: ['merchant', campaignId] })
  void qc.invalidateQueries({ queryKey: ['merchant-stock', campaignId] })
}

function invalidateShopTxn(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  invalidateMerchants(qc, campaignId)
  void qc.invalidateQueries({ queryKey: ['party', campaignId] })
  void qc.invalidateQueries({ queryKey: ['items', campaignId] })
  void qc.invalidateQueries({ queryKey: ['events', campaignId] })
  void qc.invalidateQueries({ queryKey: ['timeline', campaignId] })
  void qc.invalidateQueries({ queryKey: ['dashboard', campaignId] })
}

export function useMerchants(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['merchants', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/merchants', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load merchants',
      ),
  })
}

// A merchant's id *is* its wiki entity id, so this doubles as "the shop for this entity".
export function useMerchant(campaignId: string | null, merchantId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!merchantId,
    queryKey: ['merchant', campaignId, merchantId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}', {
          params: { path: { campaign_id: campaignId!, merchant_id: merchantId! } },
        }),
        'load merchant',
      ),
  })
}

export function useCreateMerchant(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: MerchantCreate) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/merchants', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create merchant',
      ),
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useUpdateMerchant(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { merchantId: string } & MerchantUpdate) => {
      const { merchantId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId } },
          body,
        }),
        'update merchant',
      )
    },
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useDeleteMerchant(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (merchantId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId } },
        }),
        'delete merchant',
      ),
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useMerchantStock(campaignId: string | null, merchantId: string | null) {
  return useQuery({
    enabled: !!campaignId && !!merchantId,
    queryKey: ['merchant-stock', campaignId, merchantId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/stock', {
          params: { path: { campaign_id: campaignId!, merchant_id: merchantId! } },
        }),
        'load stock',
      ),
  })
}

export function useAddStock(campaignId: string, merchantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: components['schemas']['StockLineCreate']) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/stock', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId } },
          body,
        }),
        'add stock',
      ),
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useUpdateStock(campaignId: string, merchantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { lineId: string } & components['schemas']['StockLineUpdate']) => {
      const { lineId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/stock/{line_id}', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId, line_id: lineId } },
          body,
        }),
        'update stock',
      )
    },
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useRemoveStock(campaignId: string, merchantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (lineId: string) =>
      unwrap(
        await api.DELETE('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/stock/{line_id}', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId, line_id: lineId } },
        }),
        'remove stock',
      ),
    onSuccess: () => invalidateMerchants(qc, campaignId),
  })
}

export function useBuyItem(campaignId: string, merchantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { lineId: string; quantity?: number }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/stock/{line_id}/buy', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId, line_id: vars.lineId } },
          body: { quantity: vars.quantity ?? 1 },
        }),
        'buy item',
      ),
    onSuccess: () => invalidateShopTxn(qc, campaignId),
  })
}

export function useSellItem(campaignId: string, merchantId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (itemId: string) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/merchants/{merchant_id}/sell', {
          params: { path: { campaign_id: campaignId, merchant_id: merchantId } },
          body: { item_id: itemId },
        }),
        'sell item',
      ),
    onSuccess: () => invalidateShopTxn(qc, campaignId),
  })
}

// --- story engine (FR-4) ----------------------------------------------------
// The GM authors a graph of beats; the engine only *suggests* which are reachable
// (backend service.py:146). Activating a beat runs its consequences, which reach into
// quests, NPCs and flags — hence the wide invalidation on the status mutation.
export function useStoryGraph(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['story-graph', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/story/graph', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load story graph',
      ),
  })
}

export function useStorySuggestions(campaignId: string | null) {
  return useQuery({
    enabled: !!campaignId,
    queryKey: ['story-suggestions', campaignId],
    queryFn: async () =>
      unwrap(
        await api.GET('/api/v1/campaigns/{campaign_id}/story/suggestions', {
          params: { path: { campaign_id: campaignId! } },
        }),
        'load story suggestions',
      ),
  })
}

// A query rather than a mutation: the check is a pure read of campaign state, so it caches
// per-expression and a flag write can invalidate every displayed truth value at once.
export function useConditionCheck(campaignId: string | null, expr: string) {
  return useQuery({
    enabled: !!campaignId && expr.trim() !== '',
    queryKey: ['story-condition', campaignId, expr],
    queryFn: async () =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/story/conditions/check', {
          params: { path: { campaign_id: campaignId! } },
          body: { expr },
        }),
        'check condition',
      ),
  })
}

function invalidateStory(qc: ReturnType<typeof useQueryClient>, campaignId: string) {
  void qc.invalidateQueries({ queryKey: ['story-graph', campaignId] })
  void qc.invalidateQueries({ queryKey: ['story-suggestions', campaignId] })
  void qc.invalidateQueries({ queryKey: ['story-condition', campaignId] })
}

export function useSetStoryFlag(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { key: string; value: unknown }) =>
      unwrap(
        await api.PUT('/api/v1/campaigns/{campaign_id}/story/flags', {
          params: { path: { campaign_id: campaignId } },
          body: { key: vars.key, value: vars.value },
        }),
        'set flag',
      ),
    onSuccess: () => invalidateStory(qc, campaignId),
  })
}

export function useCreateStoryNode(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: StoryNodeIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/story/nodes', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create story node',
      ),
    onSuccess: () => {
      invalidateStory(qc, campaignId)
      invalidateCampaign(qc, campaignId) // a beat is also a wiki entity
    },
  })
}

// Position writes deliberately patch the cache instead of invalidating: a refetch mid-drag
// replaces the node array and the canvas snaps back. Consequence edits do invalidate.
export function useUpdateStoryNode(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { nodeId: string } & StoryNodeUpdate) => {
      const { nodeId, ...body } = vars
      return unwrap(
        await api.PATCH('/api/v1/campaigns/{campaign_id}/story/nodes/{node_id}', {
          params: { path: { campaign_id: campaignId, node_id: nodeId } },
          body,
        }),
        'update story node',
      )
    },
    onSuccess: (node, vars) => {
      qc.setQueryData(['story-graph', campaignId], (prev: StoryGraph | undefined) =>
        prev
          ? { ...prev, nodes: prev.nodes.map((n) => (n.entity_id === node.entity_id ? node : n)) }
          : prev,
      )
      if (vars.consequences !== undefined) invalidateStory(qc, campaignId)
    },
  })
}

export function useSetStoryNodeStatus(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (vars: { nodeId: string; status: string }) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/story/nodes/{node_id}/status', {
          params: { path: { campaign_id: campaignId, node_id: vars.nodeId } },
          body: { status: vars.status },
        }),
        'set story node status',
      ),
    onSuccess: () => {
      // Consequences can move quests, relocate NPCs, set flags and write the timeline.
      invalidateStory(qc, campaignId)
      invalidateQuests(qc, campaignId)
      invalidateCampaign(qc, campaignId)
      void qc.invalidateQueries({ queryKey: ['npcs', campaignId] })
    },
  })
}

export function useDeleteStoryNode(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (nodeId: string) => {
      const { error } = await api.DELETE('/api/v1/campaigns/{campaign_id}/story/nodes/{node_id}', {
        params: { path: { campaign_id: campaignId, node_id: nodeId } },
      })
      if (error) throw new Error('delete story node')
    },
    onSuccess: () => {
      invalidateStory(qc, campaignId)
      invalidateCampaign(qc, campaignId)
    },
  })
}

export function useCreateStoryEdge(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: StoryEdgeIn) =>
      unwrap(
        await api.POST('/api/v1/campaigns/{campaign_id}/story/edges', {
          params: { path: { campaign_id: campaignId } },
          body,
        }),
        'create story edge',
      ),
    onSuccess: () => invalidateStory(qc, campaignId),
  })
}

export function useDeleteStoryEdge(campaignId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (edgeId: string) => {
      const { error } = await api.DELETE('/api/v1/campaigns/{campaign_id}/story/edges/{edge_id}', {
        params: { path: { campaign_id: campaignId, edge_id: edgeId } },
      })
      if (error) throw new Error('delete story edge')
    },
    onSuccess: () => invalidateStory(qc, campaignId),
  })
}
