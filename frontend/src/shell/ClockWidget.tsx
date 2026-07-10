import { useEffect, useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { previewAdvance, useAdvanceTime, useClock, useSetRealtime } from '../api/hooks'
import { CalendarMath } from '../lib/calendar'
import type { CalendarDef } from '../lib/calendar'
import { useActiveCampaign } from './useActiveCampaign'
import type { components } from '../api/schema'

type AdvanceReport = components['schemas']['AdvanceReport']
type FiredEvent = components['schemas']['FiredEvent']

// Always-visible campaign clock (docs/09, §11.1). When real-time is on and no combat is
// running, the display ticks forward each real second (formatted locally from the
// calendar); combat pauses it and drives the clock at 6s/round.
export function ClockWidget() {
  const { campaign } = useActiveCampaign()
  const campaignId = campaign?.id ?? null
  const qc = useQueryClient()
  const { data: clock, dataUpdatedAt } = useClock(campaignId)
  const advance = useAdvanceTime(campaignId ?? '')
  const realtime = useSetRealtime(campaignId ?? '')

  const [open, setOpen] = useState(false)
  const [days, setDays] = useState(0)
  const [hours, setHours] = useState(0)
  const [report, setReport] = useState<AdvanceReport | null>(null)
  const [preview, setPreview] = useState<FiredEvent[] | null>(null)
  const [nowTick, setNowTick] = useState(Date.now())

  const ticking = Boolean(clock?.realtime_enabled && !clock?.realtime_paused)

  // Re-render each second while real time ticks, and periodically re-sync with the server.
  useEffect(() => {
    if (!ticking || !campaignId) return
    const id = setInterval(() => {
      setNowTick(Date.now())
      // Re-anchor from the server every ~10s so client + server never drift far.
      if (Date.now() - dataUpdatedAt > 10_000) {
        void qc.invalidateQueries({ queryKey: ['clock', campaignId] })
      }
    }, 1000)
    return () => clearInterval(id)
  }, [ticking, campaignId, dataUpdatedAt, qc])

  const cal = useMemo(
    () => (clock ? new CalendarMath(clock.calendar as unknown as CalendarDef) : null),
    [clock],
  )

  if (!clock || !cal) return <div className="clock muted">…</div>

  const displaySeconds = ticking
    ? clock.time_game + Math.floor((nowTick - dataUpdatedAt) / 1000)
    : clock.time_game
  const shown = cal.format(displaySeconds)

  const doAdvance = (d: number, h: number, reason: string) => {
    if (d <= 0 && h <= 0) return
    advance.mutate({ days: d, hours: h, reason }, { onSuccess: (r) => { setReport(r); setPreview(null) } })
  }

  const doPreview = async () => {
    if (!campaignId || (days <= 0 && hours <= 0)) return
    const result = await previewAdvance(campaignId, { days, hours })
    setPreview(result?.would_fire ?? [])
    setReport(null)
  }

  return (
    <div className="clock">
      <button className="clock-face" onClick={() => setOpen((o) => !o)} title="Advance time">
        <span className="clock-date">
          {clock.realtime_paused ? '⚔ ' : ticking ? '● ' : ''}{shown.label}
        </span>
        <span className="clock-sub">
          {shown.weekday} · {shown.time}
          {shown.season ? ` · ${shown.season}` : ''}
        </span>
      </button>

      {open && (
        <div className="clock-menu" onMouseLeave={() => setOpen(false)}>
          <label className="row muted" style={{ gap: 6, marginBottom: 8 }}>
            <input
              type="checkbox"
              checked={Boolean(clock.realtime_enabled)}
              onChange={(e) => realtime.mutate(e.target.checked)}
            />
            Real-time clock {clock.realtime_paused ? '(paused: combat)' : ''}
          </label>
          <div className="clock-quick">
            <button onClick={() => doAdvance(0, 1, 'wait')}>+1h</button>
            <button onClick={() => doAdvance(0, 8, 'long rest')}>+8h</button>
            <button onClick={() => doAdvance(1, 0, 'wait')}>+1 day</button>
            <button onClick={() => doAdvance(7, 0, 'travel')}>+1 week</button>
          </div>
          <div className="clock-custom row">
            <label>
              d
              <input type="number" min={0} value={days} onChange={(e) => setDays(+e.target.value)} />
            </label>
            <label>
              h
              <input type="number" min={0} value={hours} onChange={(e) => setHours(+e.target.value)} />
            </label>
            <button className="ghost" disabled={days <= 0 && hours <= 0} onClick={() => void doPreview()}>
              Preview
            </button>
            <button
              disabled={advance.isPending || (days <= 0 && hours <= 0)}
              onClick={() => {
                doAdvance(days, hours, 'manual')
                setDays(0)
                setHours(0)
              }}
            >
              Advance
            </button>
          </div>

          {preview && (
            <div className="advance-report">
              <div className="muted">Would fire ({preview.length}):</div>
              {preview.length > 0 ? (
                <ul>
                  {preview.map((f, i) => (
                    <li key={`${f.scheduled_event_id}:${i}`}>
                      <strong>{f.at_label}</strong> — {f.narrative}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="muted">Nothing scheduled in that window.</div>
              )}
            </div>
          )}

          {report && (
            <div className="advance-report">
              <div className="muted">Now: {report.formatted.label} ({report.formatted.time})</div>
              {(report.fired ?? []).length > 0 ? (
                <ul>
                  {(report.fired ?? []).map((f) => (
                    <li key={f.scheduled_event_id}>
                      <strong>{f.at_label}</strong> — {f.narrative}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="muted">Nothing scheduled fired.</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
