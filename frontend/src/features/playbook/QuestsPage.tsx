import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useAddQuestDependency,
  useClock,
  useCreateQuest,
  useQuestGraph,
  useQuests,
  useRemoveQuestDependency,
  useSetQuestDeadline,
  useSetQuestStatus,
  useToggleObjective,
} from '../../api/hooks'
import { useActiveCampaign } from '../../shell/useActiveCampaign'
import { useCalendar } from '../../lib/useCalendar'
import { QuestGraphView } from './QuestGraphView'
import type { Quest } from '../../api/client'

// The quest board (FR-10): a kanban of the status machine, plus the dependency DAG.
// Columns mirror the backend's legal transitions — a card only offers moves it can make.
const COLUMNS: { status: string; label: string }[] = [
  { status: 'unknown', label: 'Unknown' },
  { status: 'available', label: 'Available' },
  { status: 'active', label: 'Active' },
  { status: 'completed', label: 'Completed' },
]
const RESOLVED = ['failed', 'expired', 'abandoned']

const NEXT: Record<string, string[]> = {
  unknown: ['available', 'active'],
  available: ['active', 'abandoned'],
  active: ['completed', 'failed', 'abandoned'],
  completed: [],
  failed: [],
  expired: [],
  abandoned: ['active'],
}

export function QuestsPage() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const { data: quests } = useQuests(campaignId)
  const [view, setView] = useState<'board' | 'graph'>('board')
  const { data: graph } = useQuestGraph(campaignId, view === 'graph')
  const [selected, setSelected] = useState<string | null>(null)
  const create = useCreateQuest(campaignId ?? '')
  const [name, setName] = useState('')

  if (!campaign) return <p className="muted">Select a campaign to begin.</p>

  const all = quests ?? []
  const resolved = all.filter((q) => RESOLVED.includes(q.status))
  const detail = selected ? all.find((q) => q.entity_id === selected) ?? null : null

  return (
    <>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 12 }}>
        <h2 style={{ margin: 0 }}>Quests</h2>
        <div className="row" style={{ gap: 6 }}>
          <button className={view === 'board' ? '' : 'ghost'} onClick={() => setView('board')}>
            Board
          </button>
          <button className={view === 'graph' ? '' : 'ghost'} onClick={() => setView('graph')}>
            Graph
          </button>
        </div>
      </div>

      <form
        className="card"
        onSubmit={(e) => {
          e.preventDefault()
          if (!name.trim()) return
          create.mutate({ name: name.trim() }, { onSuccess: () => setName('') })
        }}
      >
        <div className="row" style={{ gap: 10 }}>
          <input
            placeholder="New quest…"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ flex: 1 }}
          />
          <button type="submit" disabled={!name.trim() || create.isPending}>Add quest</button>
        </div>
      </form>

      {view === 'graph' && graph && (
        <QuestGraphView graph={graph} onSelect={setSelected} />
      )}

      {view === 'board' && (
        <div className="quest-board">
          {COLUMNS.map((col) => (
            <div key={col.status} className="quest-col">
              <h4>
                {col.label}
                <span className="muted"> {all.filter((q) => q.status === col.status).length}</span>
              </h4>
              {all
                .filter((q) => q.status === col.status)
                .map((q) => (
                  <QuestCard
                    key={q.entity_id}
                    campaignId={campaign.id}
                    quest={q}
                    onOpen={() => setSelected(q.entity_id)}
                  />
                ))}
            </div>
          ))}
        </div>
      )}

      {view === 'board' && resolved.length > 0 && (
        <div className="card" style={{ marginTop: 12 }}>
          <h4 style={{ marginTop: 0 }}>Resolved</h4>
          <ul className="entities">
            {resolved.map((q) => (
              <li key={q.entity_id}>
                <Link to="/entities/$entityId" params={{ entityId: q.entity_id }}>{q.name}</Link>
                <span className={`badge quest-${q.status}`}>{q.status}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {detail && (
        <QuestDetail campaignId={campaign.id} quest={detail} all={all} onClose={() => setSelected(null)} />
      )}
    </>
  )
}

function QuestCard({
  campaignId,
  quest,
  onOpen,
}: {
  campaignId: string
  quest: Quest
  onOpen: () => void
}) {
  const setStatus = useSetQuestStatus(campaignId)
  const done = quest.objectives.filter((o) => o.done).length

  return (
    <div className={'quest-card card' + (quest.overdue ? ' overdue' : '')}>
      <button className="linkish" onClick={onOpen}>{quest.name}</button>
      <div className="row" style={{ gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
        <span className="badge">{quest.quest_type}</span>
        {quest.objectives.length > 0 && (
          <span className="muted" style={{ fontSize: 12 }}>{done}/{quest.objectives.length}</span>
        )}
        {quest.deadline_label && (
          <span className={'badge' + (quest.overdue ? ' diff-deadly' : '')} title="deadline">
            ⌛ {quest.deadline_label}
          </span>
        )}
        {quest.blocked_by.length > 0 && (
          <span className="badge diff-hard" title="prerequisites unfinished">
            blocked ×{quest.blocked_by.length}
          </span>
        )}
      </div>
      <div className="row" style={{ gap: 4, marginTop: 6 }}>
        {NEXT[quest.status]?.map((next) => (
          <button
            key={next}
            className="ghost"
            style={{ fontSize: 11 }}
            onClick={() => setStatus.mutate({ questId: quest.entity_id, status: next })}
          >
            → {next}
          </button>
        ))}
      </div>
    </div>
  )
}

function QuestDetail({
  campaignId,
  quest,
  all,
  onClose,
}: {
  campaignId: string
  quest: Quest
  all: Quest[]
  onClose: () => void
}) {
  const { data: clock } = useClock(campaignId)
  const cal = useCalendar(campaignId)
  const toggle = useToggleObjective(campaignId)
  const setDeadline = useSetQuestDeadline(campaignId)
  const addDep = useAddQuestDependency(campaignId)
  const removeDep = useRemoveQuestDependency(campaignId)
  const [days, setDays] = useState('7')
  const [dep, setDep] = useState('')
  const [err, setErr] = useState<string | null>(null)

  // Deadlines are entered as "N days from now" — the absolute campaign time is derived
  // from the live clock, so the GM never has to think in seconds-since-epoch.
  const armDeadline = () => {
    if (!clock || !cal) return
    const n = Number(days)
    if (!Number.isFinite(n)) return
    setDeadline.mutate({
      questId: quest.entity_id,
      deadline: clock.time_game + Math.round(n * cal.secondsPerDay),
    })
  }

  const candidates = all.filter(
    (q) => q.entity_id !== quest.entity_id && !quest.depends_on.includes(q.entity_id),
  )
  const nameOf = (id: string) => all.find((q) => q.entity_id === id)?.name ?? id

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>
          <Link to="/entities/$entityId" params={{ entityId: quest.entity_id }}>{quest.name}</Link>
        </h3>
        <button className="ghost tag-x" onClick={onClose}>×</button>
      </div>
      <p className="muted">{quest.summary ?? 'No summary.'}</p>

      <h4>Objectives</h4>
      {quest.objectives.length === 0 && <p className="muted">None.</p>}
      <ul className="objectives">
        {quest.objectives.map((o, i) => (
          <li key={i}>
            <label>
              <input
                type="checkbox"
                checked={o.done}
                onChange={(e) =>
                  toggle.mutate({ questId: quest.entity_id, index: i, done: e.target.checked })
                }
              />
              <span className={o.done ? 'done' : ''}>{o.text}</span>
            </label>
          </li>
        ))}
      </ul>

      <h4>Deadline</h4>
      <div className="row" style={{ gap: 6 }}>
        {quest.deadline_label ? (
          <span className={'badge' + (quest.overdue ? ' diff-deadly' : '')}>
            ⌛ {quest.deadline_label}
          </span>
        ) : (
          <span className="muted">None set.</span>
        )}
        <input
          value={days}
          onChange={(e) => setDays(e.target.value)}
          style={{ width: 60 }}
          aria-label="days from now"
        />
        <button onClick={armDeadline}>Set in N days</button>
        {quest.deadline_game !== null && (
          <button
            className="ghost"
            onClick={() => setDeadline.mutate({ questId: quest.entity_id, deadline: null })}
          >
            Clear
          </button>
        )}
      </div>

      <h4>Depends on</h4>
      <ul className="entities">
        {quest.depends_on.map((id) => (
          <li key={id}>
            <span>{nameOf(id)}</span>
            <span className="row" style={{ gap: 6 }}>
              {quest.blocked_by.includes(id) && <span className="badge diff-hard">unfinished</span>}
              <button
                className="ghost tag-x"
                onClick={() => removeDep.mutate({ questId: quest.entity_id, dependsOnId: id })}
              >
                ×
              </button>
            </span>
          </li>
        ))}
        {quest.depends_on.length === 0 && <p className="muted">Nothing — this quest is a root.</p>}
      </ul>
      <div className="row" style={{ gap: 6 }}>
        <select value={dep} onChange={(e) => setDep(e.target.value)}>
          <option value="">— add a prerequisite —</option>
          {candidates.map((q) => (
            <option key={q.entity_id} value={q.entity_id}>{q.name}</option>
          ))}
        </select>
        <button
          disabled={!dep}
          onClick={() => {
            setErr(null)
            addDep.mutate(
              { questId: quest.entity_id, dependsOnId: dep },
              { onSuccess: () => setDep(''), onError: (e) => setErr((e as Error).message) },
            )
          }}
        >
          Link
        </button>
      </div>
      {err && <p className="tag danger" style={{ marginTop: 8 }}>{err}</p>}
    </div>
  )
}
