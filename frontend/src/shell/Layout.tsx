import { useEffect } from 'react'
import { Link, Outlet } from '@tanstack/react-router'
import { CampaignSwitcher } from './CampaignSwitcher'
import { ClockWidget } from './ClockWidget'
import { CommandPalette } from './CommandPalette'
import { EntityPeek } from './EntityPeek'
import { NotificationsWidget } from './NotificationsWidget'
import { useUiStore } from '../stores/ui'
import { useActiveCampaign } from './useActiveCampaign'

// The application shell (docs/09-ui-architecture.md, §11.1): top bar (search + campaign
// switcher) + left nav + routed main view, with the ⌘K palette and peek panel overlaid.
export function Layout() {
  const { campaign } = useActiveCampaign()
  const setPaletteOpen = useUiStore((s) => s.setPaletteOpen)
  const paletteOpen = useUiStore((s) => s.paletteOpen)

  // Global ⌘K / Ctrl+K toggles the command palette from anywhere (NFR-3.2).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen(!useUiStore.getState().paletteOpen)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setPaletteOpen])

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Campaign Nexus</span>
        <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
          <span>Search…</span>
          <kbd>⌘K</kbd>
        </button>
        <ClockWidget />
        {campaign && <NotificationsWidget campaignId={campaign.id} />}
        <CampaignSwitcher />
      </header>
      <nav className="nav">
        <Link to="/" activeOptions={{ exact: true }}>
          Dashboard
        </Link>
        <Link to="/entities">Entities</Link>
        <Link to="/party">Party</Link>
        <Link to="/npcs">NPCs</Link>
        <Link to="/equipment">Equipment</Link>
        <Link to="/merchants">Merchants</Link>
        <Link to="/timeline">Timeline</Link>
        <Link to="/sessions">Sessions</Link>

        <Link to="/bestiary">Bestiary</Link>
        <Link to="/spells">Spells</Link>
        <Link to="/quests">Quests</Link>
        <Link to="/encounters">Encounters</Link>
        <Link to="/skill-challenges">Skill Challenges</Link>
        <Link to="/random-tables">Tables</Link>
        <Link to="/combat">Combat</Link>
        <Link to="/schedule">Schedule</Link>
        <Link to="/data">Data</Link>
        <div className="nav-group">Browse</div>
        <Link to="/entities" search={{ type: 'location' }}>
          Locations
        </Link>
        <Link to="/entities" search={{ type: 'faction' }}>
          Factions
        </Link>
        <Link to="/entities" search={{ type: 'quest' }}>
          Quests
        </Link>
      </nav>
      <main className="main">
        <Outlet />
      </main>
      {paletteOpen && <CommandPalette />}
      <EntityPeek />
    </div>
  )
}
