import { Link, useNavigate } from '@tanstack/react-router'
import {
  useEncounter,
  useEncounterCombats,
  useMonsters,
  useStartCombat,
} from '../../api/hooks'
import { crLabel } from './CreaturePicker'

const DIFF_CLASS: Record<string, string> = {
  trivial: 'diff-trivial', easy: 'diff-easy', medium: 'diff-medium',
  hard: 'diff-hard', deadly: 'diff-deadly',
}

// Shown on an `encounter` entity's page: makes the structured encounter data visible (its
// roster, terrain, tactics, difficulty) and wires it to the combat tracker — start a new
// combat or jump to one already running. Editing is its own page (EncounterEditorPage).
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
          <Link to="/encounters/$entityId/edit" params={{ entityId }} className="ghost"
                style={{ padding: '6px 10px' }}>
            Edit
          </Link>
          <button disabled={startCombat.isPending} onClick={start}>
            {startCombat.isPending ? 'Starting…' : 'Start combat'}
          </button>
        </div>
      </div>

      {encounter.combatants.length === 0 ? (
        <p className="muted">Nothing in this encounter yet — press Edit to add some.</p>
      ) : (
        <ul className="roster">
          {encounter.combatants.map((c) => (
            <li key={c.npc_id ?? c.monster_id} className="row" style={{ gap: 8 }}>
              <span className="roster-count">{c.count}×</span>
              <span style={{ flex: 1 }}>{c.name}</span>
              {c.side === 'ally' && <span className="tag">ally</span>}
              {c.npc_id ? (
                // An NPC with no sheet stays on the roster but never reaches the order —
                // worth saying here, since the combat tracker simply won't show them.
                <span className={'badge' + (c.has_stats ? '' : ' diff-hard')}>
                  {c.has_stats ? 'NPC' : 'NPC · no sheet'}
                </span>
              ) : (
                <span className="badge">CR {crLabel(crOf(c.monster_id!))}</span>
              )}
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

      {(encounter.environment?.length ?? 0) > 0 && (
        <div style={{ marginTop: 8 }}>
          <h4 style={{ margin: '0 0 4px' }}>Environmental actions</h4>
          <ul className="roster">
            {encounter.environment!.map((e, i) => (
              <li key={i} style={{ display: 'block' }}>
                <b>{e.name}</b>
                {e.initiative != null && <span className="muted"> · init {e.initiative}</span>}
                {(e.actions?.length ?? 0) > 0 && (
                  <ul className="muted" style={{ fontSize: 12, margin: '2px 0 0 16px' }}>
                    {e.actions!.map((a, n) => (
                      <li key={n}>
                        <b>{a.name}</b>{a.description ? ` — ${a.description}` : ''}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Associated combat runs */}
      {(combats?.length ?? 0) > 0 && (
        <div style={{ marginTop: 10 }}>
          <h4 style={{ margin: '0 0 6px' }}>Combat</h4>
          <ul className="entities">
            {combats!.map((run) => (
              <li key={run.run_id}>
                {/* Test against 'completed', not 'active': a run sitting in `setup` (rolling
                    initiative) is unfinished, and reading it as Completed would be a lie. */}
                <button className="linkish" onClick={() => openRun(run.run_id)}>
                  {run.status === 'completed'
                    ? 'Completed'
                    : run.status === 'setup'
                      ? 'Rolling initiative'
                      : `In progress — round ${run.round}`}
                </button>
                <span className={'badge ' + (run.status === 'completed' ? '' : 'diff-hard')}>
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
