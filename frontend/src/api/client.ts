// The typed API client. Types come from src/api/schema.d.ts, which is generated from
// the backend's OpenAPI spec (`npm run gen:api`) — so backend contract changes surface
// as TypeScript errors here (NFR-4.3, ADR-006).
import createClient from 'openapi-fetch'
import type { components } from './schema'
import type { paths } from './schema'

export const api = createClient<paths>({ baseUrl: '/' })

// Convenience aliases for the component schemas the UI consumes.
export type Campaign = components['schemas']['CampaignOut']
export type CampaignCreate = components['schemas']['CampaignCreate']
export type RuleSystem = components['schemas']['RuleSystemInfo']
export type StatBlock = components['schemas']['StatBlockOut']
export type Monster = components['schemas']['MonsterOut']
export type FacetDef = components['schemas']['FacetDefOut']
export type Encounter = components['schemas']['EncounterOut']
export type Entity = components['schemas']['EntityOut']
export type EntityDetail = components['schemas']['EntityDetail']
export type EntityCreate = components['schemas']['EntityCreate']
export type EntityUpdate = components['schemas']['EntityUpdate']
export type LinkRef = components['schemas']['LinkRef']
export type EntityRef = components['schemas']['EntityRef']
export type LinkType = components['schemas']['LinkTypeOut']
export type Tag = components['schemas']['TagOut']
export type Event = components['schemas']['EventOut']
export type Dashboard = components['schemas']['DashboardOut']
export type EntityBrief = components['schemas']['EntityBrief']
export type EventBrief = components['schemas']['EventBrief']
export type MapSummary = components['schemas']['MapSummary']
export type MapDetail = components['schemas']['MapDetail']
export type MapMarker = components['schemas']['MarkerOut']
export type AttachmentOut = components['schemas']['AttachmentOut']
export type MapRegion = components['schemas']['RegionOut']
export type ReferencesOut = components['schemas']['ReferencesOut']
export type ArticleSnapshot = components['schemas']['ArticleSnapshotOut']
export type Backup = components['schemas']['BackupOut']
export type Npc = components['schemas']['NpcOut']
export type NpcHistoryRow = components['schemas']['HistoryRow']
export type NpcSchedule = components['schemas']['ScheduleOut']
export type TravelPlan = components['schemas']['TravelPlan']
export type Quest = components['schemas']['QuestOut']
export type QuestBrief = components['schemas']['QuestBrief']
export type QuestGraph = components['schemas']['QuestGraph']

