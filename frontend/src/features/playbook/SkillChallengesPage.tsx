import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useCreateSkillChallenge,
  useRecordSkillCheck,
  useSkillChallenges,
  useSkillRun,
  useSkillRunAction,
  useStartSkillRun,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import type { GraduatedOutcome, SkillApproach, SkillChallenge } from '../../api/client'

// The canonical difficulty ladder (mirrors backend DIFFICULTY_TIERS). The concrete DC for
// each tier is system-specific and comes back on the challenge as `dcs`.
const TIERS = ['trivial', 'easy', 'normal', 'hard', 'very_hard', 'nearly_impossible'] as const
const TIER_LABEL: Record<string, string> = {
  trivial: 'Trivial', easy: 'Easy', normal: 'Normal',
  hard: 'Hard', very_hard: 'Very Hard', nearly_impossible: 'Nearly Impossible',
}

// Skill challenges (FR-12): a system-agnostic, graduated non-combat scene. Build a challenge,
// then run it live at the table — recording each check and reading the outcome tier the
// party's failure count lands on.
export function SkillChallengesPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: challenges } = useSkillChallenges(campaignId)
  const [running, setRunning] = useState<SkillChallenge | null>(null)

  return (
    <>
      <h2>Skill Challenges</h2>
      <p className="muted" style={{ marginTop: -6 }}>
        Graduated non-combat scenes: run checks until the scene resolves, then read the
        outcome the party's failures earned. Difficulty tiers are priced into DCs by this
        campaign's rule system.
      </p>

      {campaignId && <CreateForm campaignId={campaignId} />}

      <ul className="entities">
        {challenges?.map((ch) => (
          <li key={ch.id}>
            <Link to="/entities/$entityId" params={{ entityId: ch.id }}>{ch.name}</Link>
            <span className="row" style={{ gap: 8 }}>
              <span className="muted">
                {ch.total_checks > 0
                  ? `${ch.total_checks} checks`
                  : ch.failure_cap
                    ? `race · ${ch.failure_cap} failures`
                    : 'open'}
              </span>
              <span className="muted">{ch.outcomes.length} outcomes</span>
              <button type="button" onClick={() => setRunning(ch)}>Run</button>
            </span>
          </li>
        ))}
        {challenges?.length === 0 && <p className="muted">No skill challenges yet.</p>}
      </ul>

      {running && campaignId && (
        <RunTracker
          campaignId={campaignId}
          challenge={running}
          onClose={() => setRunning(null)}
        />
      )}
    </>
  )
}

// --------------------------------------------------------------------------- //
// Authoring
// --------------------------------------------------------------------------- //
function CreateForm({ campaignId }: { campaignId: string }) {
  const create = useCreateSkillChallenge(campaignId)
  const [name, setName] = useState('')
  const [premise, setPremise] = useState('')
  const [totalChecks, setTotalChecks] = useState(5)
  const [approaches, setApproaches] = useState<SkillApproach[]>([
    { skill: '', difficulty: 'normal', hint: '' },
  ])
  const [outcomes, setOutcomes] = useState<GraduatedOutcome[]>([
    { min_failures: 0, label: '', narrative: '', effects: [] },
  ])

  const reset = () => {
    setName(''); setPremise(''); setTotalChecks(5)
    setApproaches([{ skill: '', difficulty: 'normal', hint: '' }])
    setOutcomes([{ min_failures: 0, label: '', narrative: '', effects: [] }])
  }

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    create.mutate(
      {
        name: name.trim(),
        premise: premise.trim() || null,
        total_checks: totalChecks,
        approaches: approaches.filter((a) => a.skill.trim()),
        outcomes: outcomes
          .filter((o) => o.label?.trim())
          .map((o) => ({ ...o, label: o.label!.trim() })),
      },
      { onSuccess: reset },
    )
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <input placeholder="Challenge name" value={name}
          onChange={(e) => setName(e.target.value)} style={{ flex: 1 }} />
        <label className="row" style={{ gap: 6 }}>
          Checks to resolve
          <input type="number" min={0} value={totalChecks} style={{ width: 64 }}
            onChange={(e) => setTotalChecks(Math.max(0, Number(e.target.value)))} />
        </label>
      </div>
      <textarea placeholder="Premise / read-aloud (optional)" value={premise}
        onChange={(e) => setPremise(e.target.value)} rows={2} style={{ marginTop: 8, width: '100%' }} />

      <h4 style={{ margin: '12px 0 6px' }}>Approaches</h4>
      {approaches.map((a, i) => (
        <div key={i} className="row" style={{ gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          <input placeholder="Skill (e.g. Perception)" value={a.skill}
            onChange={(e) => setApproaches(upd(approaches, i, { skill: e.target.value }))} />
          <select value={a.difficulty ?? 'normal'}
            onChange={(e) => setApproaches(upd(approaches, i, { difficulty: e.target.value }))}>
            {TIERS.map((t) => <option key={t} value={t}>{TIER_LABEL[t]}</option>)}
          </select>
          <input placeholder="Hint (optional)" value={a.hint ?? ''} style={{ flex: 1 }}
            onChange={(e) => setApproaches(upd(approaches, i, { hint: e.target.value }))} />
          <button type="button" className="tag-x"
            onClick={() => setApproaches(approaches.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button type="button" onClick={() =>
        setApproaches([...approaches, { skill: '', difficulty: 'normal', hint: '' }])}>
        + approach
      </button>

      <h4 style={{ margin: '12px 0 6px' }}>Graduated outcomes (by failures)</h4>
      {outcomes.map((o, i) => (
        <div key={i} className="row" style={{ gap: 6, marginBottom: 6, flexWrap: 'wrap' }}>
          <label className="row" style={{ gap: 4 }}>
            ≥
            <input type="number" min={0} value={o.min_failures} style={{ width: 52 }}
              onChange={(e) =>
                setOutcomes(upd(outcomes, i, { min_failures: Math.max(0, Number(e.target.value)) }))} />
            fails
          </label>
          <input placeholder="Label" value={o.label ?? ''}
            onChange={(e) => setOutcomes(upd(outcomes, i, { label: e.target.value }))} />
          <input placeholder="Effects (comma-separated)" style={{ flex: 1 }}
            value={(o.effects ?? []).join(', ')}
            onChange={(e) => setOutcomes(upd(outcomes, i, {
              effects: e.target.value.split(',').map((s) => s.trim()).filter(Boolean),
            }))} />
          <button type="button" className="tag-x"
            onClick={() => setOutcomes(outcomes.filter((_, j) => j !== i))}>×</button>
        </div>
      ))}
      <button type="button" onClick={() =>
        setOutcomes([...outcomes, { min_failures: outcomes.length, label: '', narrative: '', effects: [] }])}>
        + outcome
      </button>

      <div>
        <button type="submit" disabled={!name.trim() || create.isPending} style={{ marginTop: 12 }}>
          Create challenge
        </button>
      </div>
    </form>
  )
}

function upd<T>(list: T[], index: number, patch: Partial<T>): T[] {
  return list.map((item, i) => (i === index ? { ...item, ...patch } : item))
}

// --------------------------------------------------------------------------- //
// Live run tracker
// --------------------------------------------------------------------------- //
function RunTracker({
  campaignId, challenge, onClose,
}: { campaignId: string; challenge: SkillChallenge; onClose: () => void }) {
  const start = useStartSkillRun(campaignId)
  const [runId, setRunId] = useState<string | null>(null)
  const { data: run } = useSkillRun(campaignId, runId)
  const record = useRecordSkillCheck(campaignId, runId ?? '')
  const undo = useSkillRunAction(campaignId, runId ?? '', 'undo')
  const resolve = useSkillRunAction(campaignId, runId ?? '', 'resolve')

  const [difficulty, setDifficulty] = useState('normal')
  const [skill, setSkill] = useState('')

  const begin = () => start.mutate(challenge.id, { onSuccess: (r) => setRunId(r.run_id) })
  const check = (outcome: string) =>
    record.mutate({ skill: skill.trim(), difficulty, outcome, dc: null, actor: null, note: null })

  return (
    <div className="card" style={{ marginTop: 16, borderColor: 'var(--accent, #888)' }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>Running: {challenge.name}</h3>
        <button type="button" className="tag-x" onClick={onClose}>×</button>
      </div>

      {challenge.premise && <p className="muted" style={{ fontStyle: 'italic' }}>{challenge.premise}</p>}

      {challenge.approaches.length > 0 && (
        <ul className="picker" style={{ marginBottom: 8 }}>
          {challenge.approaches.map((a, i) => (
            <li key={i} className="row" style={{ gap: 8, padding: '2px 0' }}>
              <strong>{a.skill}</strong>
              <span className={'badge ' + tierClass(a.difficulty ?? 'normal')}>
                {TIER_LABEL[a.difficulty ?? 'normal']} · DC {challenge.dcs[a.difficulty ?? 'normal']}
              </span>
              {a.hint && <span className="muted">{a.hint}</span>}
            </li>
          ))}
        </ul>
      )}

      {!runId ? (
        <button type="button" onClick={begin} disabled={start.isPending}>Start run</button>
      ) : run ? (
        <>
          <div className="row" style={{ gap: 16, flexWrap: 'wrap', margin: '4px 0 10px' }}>
            <Stat label="Checks" value={
              run.checks_remaining != null
                ? `${run.checks_made} / ${run.checks_made + run.checks_remaining}`
                : String(run.checks_made)} />
            <Stat label="Successes" value={String(run.successes)} />
            <Stat label="Failures" value={String(run.failures)} />
            <Stat label={run.resolved ? 'Outcome' : 'Projected'}
              value={run.outcome?.label ?? '—'} />
          </div>

          {run.outcome && (run.outcome.effects?.length ?? 0) > 0 && (
            <div className={'card ' + (run.resolved ? '' : 'muted')}
              style={{ margin: '0 0 10px', padding: '8px 12px' }}>
              {run.outcome.narrative && <p style={{ marginTop: 0 }}>{run.outcome.narrative}</p>}
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {run.outcome.effects!.map((eff, i) => <li key={i}>{eff}</li>)}
              </ul>
            </div>
          )}

          {run.resolved ? (
            <div className="row" style={{ gap: 8 }}>
              <strong>Resolved.</strong>
              <button type="button" onClick={() => undo.mutate()}>Undo last check</button>
              <button type="button" onClick={() => setRunId(null)}>New run</button>
            </div>
          ) : (
            <>
              <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
                <input placeholder="Who / skill (optional)" value={skill}
                  onChange={(e) => setSkill(e.target.value)} />
                <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
                  {TIERS.map((t) =>
                    <option key={t} value={t}>{TIER_LABEL[t]} · DC {challenge.dcs[t]}</option>)}
                </select>
              </div>
              <div className="row" style={{ gap: 8, flexWrap: 'wrap' }}>
                <button type="button" onClick={() => check('critical_success')}>Crit success</button>
                <button type="button" onClick={() => check('success')}>Success</button>
                <button type="button" onClick={() => check('failure')}>Failure</button>
                <button type="button" onClick={() => check('critical_failure')}>Crit failure</button>
                <span style={{ flex: 1 }} />
                <button type="button" onClick={() => undo.mutate()}
                  disabled={run.checks_made === 0}>Undo</button>
                <button type="button" onClick={() => resolve.mutate()}>Resolve now</button>
              </div>

              {run.checks.length > 0 && (
                <ol className="muted" style={{ margin: '10px 0 0', paddingLeft: 20 }}>
                  {run.checks.map((c, i) => (
                    <li key={i}>
                      {c.skill || 'check'} — {TIER_LABEL[c.difficulty ?? 'normal']}
                      {c.dc != null ? ` (DC ${c.dc})` : ''}: {c.outcome.replace('_', ' ')}
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}
        </>
      ) : null}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span className="muted" style={{ display: 'block', fontSize: 12 }}>{label}</span>
      <strong>{value}</strong>
    </span>
  )
}

function tierClass(tier: string): string {
  const map: Record<string, string> = {
    trivial: 'diff-trivial', easy: 'diff-easy', normal: 'diff-medium',
    hard: 'diff-hard', very_hard: 'diff-deadly', nearly_impossible: 'diff-deadly',
  }
  return map[tier] ?? ''
}
