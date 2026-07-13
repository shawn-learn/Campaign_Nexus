import { useNavigate } from '@tanstack/react-router'
import {
  useEncounter,
  useEncounterCombats,
  useMonsters,
  useStartCombat,
} from '../../api/hooks'

const DIFF_CLASS: Record<string, string> = {
  trivial: 'diff-trivial', easy: 'diff-easy', medium: 'diff-medium',
  hard: 'diff-hard', deadly: 'diff-deadly',
}

function crLabel(cr: number | null | undefined): string {
  if (cr === 0.125) return '1/8'
  if (cr === 0.25) return '1/4'
  if (cr === 0.5) return '1/2'
  return cr == null ? '?' : String(cr)
}

// Shown on an `encounter` entity's page: makes the structured encounter data visible (its
// monster roster, terrain, tactics, difficulty) and wires it to the combat tracker — start a
// new combat or jump to one already running from this encounter.
export function EncounterPanel({
  campaignId,
  entityId,
}: {
  campaignId: string
  entityId: string
}) {
  const navigate = useNavigate()
  const { data: encounter } = useEncounter(campaignId, entityId)
  const { data: monsters } = useMonsters(campaignId)
  const { data: combats } = useEncounterCombats(campaignId, entityId)
  const startCombat = useStartCombat(campaignId)

  if (!encounter) return null

  // Combat resumes from a per-campaign localStorage pointer; set it, then open the tracker.
  const openRun = (runId: string) => {
    localStorage.setItem(`nexus.combat.${campaignId}`, runId)
    void navigate({ to: '/combat' })
  }
  const start = () =>
    startCombat.mutate(entityId, { onSuccess: (run) => openRun(run.run_id) })

  const crOf = (monsterId: string) =>
    monsters?.find((m) => m.id === monsterId)?.facets.facet1_num as number | undefined
  const totalFoes = encounter.combatants
    .filter((c) => c.side !== 'ally')
    .reduce((n, c) => n + c.count, 0)

  return (
    <div className="card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0 }}>Encounter</h3>
        <div className="row" style={{ gap: 8 }}>
          {encounter.difficulty.supported && encounter.difficulty.difficulty && (
            <span className={'badge ' + (DIFF_CLASS[encounter.difficulty.difficulty] ?? '')}>
              {encounter.difficulty.difficulty}
              {encounter.difficulty.adjusted_xp != null && ` · ${encounter.difficulty.adjusted_xp} XP`}
            </span>
          )}
          <button disabled={startCombat.isPending} onClick={start}>
            {startCombat.isPending ? 'Starting…' : 'Start combat'}
          </button>
        </div>
      </div>

      {/* Monster roster preview */}
      {encounter.combatants.length === 0 ? (
        <p className="muted">No monsters in this encounter yet — add some on the Encounters page.</p>
      ) : (
        <ul className="roster">
          {encounter.combatants.map((c) => (
            <li key={c.monster_id} className="row" style={{ gap: 8 }}>
              <span className="roster-count">{c.count}×</span>
              <span style={{ flex: 1 }}>{c.name}</span>
              {c.side === 'ally' && <span className="tag">ally</span>}
              <span className="badge">CR {crLabel(crOf(c.monster_id))}</span>
            </li>
          ))}
        </ul>
      )}
      {totalFoes > 0 && (
        <p className="muted" style={{ fontSize: 12 }}>{totalFoes} foe(s) total.</p>
      )}

      {(encounter.terrain || encounter.tactics || encounter.hazards) && (
        <div style={{ marginTop: 8 }}>
          {encounter.terrain && <p style={{ margin: '2px 0' }}><b>Terrain:</b> {encounter.terrain}</p>}
          {encounter.hazards && <p style={{ margin: '2px 0' }}><b>Hazards:</b> {encounter.hazards}</p>}
          {encounter.tactics && <p style={{ margin: '2px 0' }}><b>Tactics:</b> {encounter.tactics}</p>}
        </div>
      )}

      {/* Associated combat runs */}
      {(combats?.length ?? 0) > 0 && (
        <div style={{ marginTop: 10 }}>
          <h4 style={{ margin: '0 0 6px' }}>Combat</h4>
          <ul className="entities">
            {combats!.map((run) => (
              <li key={run.run_id}>
                <button className="linkish" onClick={() => openRun(run.run_id)}>
                  {run.status === 'active' ? `In progress — round ${run.round}` : 'Completed'}
                </button>
                <span className={'badge ' + (run.status === 'active' ? 'diff-hard' : '')}>
                  {run.status}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
