import { useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useCreateSkillChallenge, useSkillChallenges } from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import type { GraduatedOutcome, SkillApproach } from '../../api/client'
import { ApproachesEditor, OutcomesEditor, emptyApproach } from './SkillChallengeFields'

// Skill challenges (FR-12): a system-agnostic, graduated non-combat scene. This page is the
// index — a challenge is designed and run on its own wiki entity page, so the whole scene
// lives in one place alongside its article and links.
export function SkillChallengesPage() {
  const { campaign } = useActiveCampaign()
  const navigate = useNavigate()
  const campaignId = campaign?.id ?? null
  const { data: challenges } = useSkillChallenges(campaignId)

  return (
    <>
      <h2>Skill Challenges</h2>
      <p className="muted" style={{ marginTop: -6 }}>
        Graduated non-combat scenes: run checks until the scene resolves, then read the
        outcome the party's failures earned. Difficulty tiers are priced into DCs by this
        campaign's rule system.
      </p>

      {campaignId && (
        <CreateForm
          campaignId={campaignId}
          onCreated={(id) =>
            navigate({ to: '/entities/$entityId', params: { entityId: id }, search: { tab: 'run' } })
          }
        />
      )}

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
              <Link
                to="/entities/$entityId"
                params={{ entityId: ch.id }}
                search={{ tab: 'run' }}
              >
                Run
              </Link>
            </span>
          </li>
        ))}
        {challenges?.length === 0 && <p className="muted">No skill challenges yet.</p>}
      </ul>
    </>
  )
}

// --------------------------------------------------------------------------- //
// Authoring
// --------------------------------------------------------------------------- //
function CreateForm({
  campaignId, onCreated,
}: { campaignId: string; onCreated: (id: string) => void }) {
  const create = useCreateSkillChallenge(campaignId)
  const [name, setName] = useState('')
  const [premise, setPremise] = useState('')
  const [totalChecks, setTotalChecks] = useState(5)
  const [approaches, setApproaches] = useState<SkillApproach[]>([{ ...emptyApproach }])
  const [outcomes, setOutcomes] = useState<GraduatedOutcome[]>([
    { min_failures: 0, label: '', narrative: '', effects: [] },
  ])

  const reset = () => {
    setName(''); setPremise(''); setTotalChecks(5)
    setApproaches([{ ...emptyApproach }])
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
      { onSuccess: (ch) => { reset(); onCreated(ch.id) } },
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
      <ApproachesEditor value={approaches} onChange={setApproaches} />

      <h4 style={{ margin: '12px 0 6px' }}>Graduated outcomes (by failures)</h4>
      <OutcomesEditor value={outcomes} onChange={setOutcomes} />

      <div>
        <button type="submit" disabled={!name.trim() || create.isPending} style={{ marginTop: 12 }}>
          {create.isPending ? 'Creating…' : 'Create challenge'}
        </button>
      </div>
    </form>
  )
}
