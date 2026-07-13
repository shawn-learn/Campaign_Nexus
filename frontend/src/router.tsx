import {
  createRootRoute,
  createRoute,
  createRouter,
} from '@tanstack/react-router'
import { Layout } from './shell/Layout'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { EntitiesPage } from './features/wiki/EntitiesPage'
import { EntityDetailPage } from './features/wiki/EntityDetailPage'
import { ScheduledEventsPage } from './features/time/ScheduledEventsPage'
import { TimelinePage } from './features/chronicle/TimelinePage'
import { SessionsPage } from './features/chronicle/SessionsPage'
import { SheetsPage } from './features/rules/SheetsPage'
import { BestiaryPage } from './features/rules/BestiaryPage'
import { PartyPage } from './features/playbook/PartyPage'
import { EncountersPage } from './features/playbook/EncountersPage'
import { SkillChallengesPage } from './features/playbook/SkillChallengesPage'
import { CombatPage } from './features/playbook/CombatPage'
import { RandomTablesPage } from './features/playbook/RandomTablesPage'
import { MapsPage } from './features/atlas/MapsPage'
import { QuestsPage } from './features/playbook/QuestsPage'
import { NpcsPage } from './features/npcs/NpcsPage'
import { DataPage } from './features/settings/DataPage'

const rootRoute = createRootRoute({ component: Layout })

const dashboardRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  component: DashboardPage,
})

const entitiesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/entities',
  validateSearch: (search: Record<string, unknown>): { type?: string } => ({
    type: typeof search.type === 'string' ? search.type : undefined,
  }),
  component: EntitiesPage,
})

const entityDetailRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/entities/$entityId',
  component: EntityDetailPage,
})

const scheduleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/schedule',
  component: ScheduledEventsPage,
})

const timelineRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/timeline',
  component: TimelinePage,
})

const sessionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/sessions',
  component: SessionsPage,
})

const sheetsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/sheets',
  component: SheetsPage,
})

const bestiaryRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/bestiary',
  // ?q=<name> seeds the search box (e.g. picking a monster in the ⌘K palette).
  validateSearch: (search: Record<string, unknown>): { q?: string } => ({
    q: typeof search.q === 'string' ? search.q : undefined,
  }),
  component: BestiaryPage,
})

const partyRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/party',
  component: PartyPage,
})

const encountersRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/encounters',
  component: EncountersPage,
})

const skillChallengesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/skill-challenges',
  component: SkillChallengesPage,
})

const combatRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/combat',
  component: CombatPage,
})

const randomTablesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/random-tables',
  component: RandomTablesPage,
})

const mapsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/maps',
  // ?open=<mapId> deep-links straight to a map (e.g. from a location's embedded map card).
  validateSearch: (search: Record<string, unknown>): { open?: string } => ({
    open: typeof search.open === 'string' ? search.open : undefined,
  }),
  component: MapsPage,
})

const questsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/quests',
  component: QuestsPage,
})

const npcsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/npcs',
  component: NpcsPage,
})

const dataRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/data',
  component: DataPage,
})

const routeTree = rootRoute.addChildren([
  dashboardRoute,
  entitiesRoute,
  entityDetailRoute,
  scheduleRoute,
  timelineRoute,
  sessionsRoute,
  sheetsRoute,
  bestiaryRoute,
  partyRoute,
  encountersRoute,
  skillChallengesRoute,
  combatRoute,
  randomTablesRoute,
  mapsRoute,
  questsRoute,
  npcsRoute,
  dataRoute,
])

export const router = createRouter({ routeTree })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
