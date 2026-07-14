import { useState, useMemo, useEffect } from 'react'
import { Link } from '@tanstack/react-router'
import {
  useClock,
  useScheduledEvents,
  useRollWeather,
  useRandomTables,
} from '../api/hooks'
import { CalendarMath } from '../lib/calendar'
import type { CalendarDef } from '../lib/calendar'

function renderDescription(text: string | null | undefined) {
  if (!text) return null
  const regex = /\[([^\]]+)\]\(([^)]+)\)/g
  const parts: React.ReactNode[] = []
  let lastIndex = 0
  let match

  while ((match = regex.exec(text)) !== null) {
    const [, linkText, url] = match
    const startIndex = match.index

    if (startIndex > lastIndex) {
      parts.push(text.slice(lastIndex, startIndex))
    }

    if (url.startsWith('/')) {
      parts.push(
        <Link
          key={startIndex}
          to={url as never}
          style={{ color: 'var(--accent, #e05252)', textDecoration: 'underline' }}
        >
          {linkText}
        </Link>
      )
    } else {
      parts.push(
        <a
          key={startIndex}
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: 'var(--accent, #e05252)', textDecoration: 'underline' }}
        >
          {linkText}
        </a>
      )
    }

    lastIndex = regex.lastIndex
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts.length > 0 ? parts : text
}

export function NotificationsWidget({ campaignId }: { campaignId: string }) {
  const { data: clock } = useClock(campaignId)
  const { data: events } = useScheduledEvents(campaignId, 'fired')
  const { data: tables } = useRandomTables(campaignId)
  const rollWeather = useRollWeather(campaignId)

  const weatherTableId = useMemo(() => {
    return tables?.find((t) => t.name === 'Barovian Weather')?.id
  }, [tables])

  const [open, setOpen] = useState(false)
  
  // Track last cleared clock time in localStorage
  const storageKey = `last_cleared_event_time_${campaignId}`
  const [lastClearedTime, setLastClearedTime] = useState<number>(() => {
    const val = localStorage.getItem(storageKey)
    return val ? Number(val) : -1
  })

  // Track individually dismissed notifications in localStorage
  const dismissedKey = `dismissed_event_ids_${campaignId}`
  const [dismissedIds, setDismissedIds] = useState<string[]>(() => {
    const val = localStorage.getItem(dismissedKey)
    return val ? JSON.parse(val) : []
  })

  // Initialize lastClearedTime to current clock time if not set yet,
  // so the user only sees events that fire AFTER their first campaign load.
  useEffect(() => {
    if (clock && lastClearedTime === -1) {
      localStorage.setItem(storageKey, String(clock.time_game))
      setLastClearedTime(clock.time_game)
    }
  }, [clock, lastClearedTime, storageKey])

  const cal = useMemo(
    () => (clock ? new CalendarMath(clock.calendar as unknown as CalendarDef) : null),
    [clock],
  )

  // Filter for unread fired events
  const unreadEvents = useMemo(() => {
    if (!events) return []
    return events.filter((e) => e.fire_at_game > lastClearedTime && !dismissedIds.includes(e.id))
  }, [events, lastClearedTime, dismissedIds])

  const handleDismissOne = (eventId: string) => {
    const next = [...dismissedIds, eventId]
    setDismissedIds(next)
    localStorage.setItem(dismissedKey, JSON.stringify(next))
  }

  const handleDismissAll = () => {
    if (!clock) return
    localStorage.setItem(storageKey, String(clock.time_game))
    setLastClearedTime(clock.time_game)
    setDismissedIds([])
    localStorage.removeItem(dismissedKey)
    setOpen(false)
  }

  const formatGameTime = (seconds: number) => {
    if (!cal) return `${seconds}s`
    const shown = cal.format(seconds)
    return `${shown.label} @ ${shown.time}`
  }

  return (
    <div className="notifications-widget" style={{ position: 'relative' }}>
      <button
        className="notifications-trigger ghost"
        onClick={() => setOpen((o) => !o)}
        title="Campaign Notifications"
        style={{
          padding: '6px 10px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          position: 'relative'
        }}
      >
        <span>🔔</span>
        {unreadEvents.length > 0 && (
          <span
            className="badge"
            style={{
              background: 'var(--danger, #e05252)',
              color: '#fff',
              fontSize: 10,
              padding: '2px 6px',
              borderRadius: 99,
              position: 'absolute',
              top: -5,
              right: -5
            }}
          >
            {unreadEvents.length}
          </span>
        )}
      </button>

      {open && (
        <div
          className="notifications-menu card"
          onMouseLeave={() => setOpen(false)}
          style={{
            position: 'absolute',
            top: '100%',
            right: 0,
            zIndex: 100,
            width: 320,
            marginTop: 8,
            padding: 12,
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            maxHeight: 400,
            overflowY: 'auto'
          }}
        >
          <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8, borderBottom: '1px solid var(--border)', paddingBottom: 6 }}>
            <span style={{ fontWeight: 600 }}>Fired Events</span>
            {unreadEvents.length > 0 && (
              <button
                className="ghost"
                onClick={handleDismissAll}
                style={{ fontSize: 11, padding: '2px 6px' }}
              >
                Dismiss All
              </button>
            )}
          </div>

          {unreadEvents.length === 0 ? (
            <div className="muted" style={{ textAlign: 'center', padding: '16px 0', fontSize: 13 }}>
              No new notifications.
            </div>
          ) : (
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
              {unreadEvents.map((e) => {
                const isWeather = e.action_type === 'cos_weather_roll'
                return (
                  <li
                    key={e.id}
                    style={{
                      borderBottom: '1px solid var(--border)',
                      paddingBottom: 8,
                      fontSize: 13
                    }}
                  >
                    <div style={{ fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>{e.title}</span>
                        {isWeather && <span className="tag" style={{ fontSize: 10 }}>Weather</span>}
                      </span>
                      <button
                        className="ghost tag-x"
                        title="Dismiss"
                        onClick={() => handleDismissOne(e.id)}
                        style={{ border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 12, padding: '2px 6px' }}
                      >
                        ×
                      </button>
                    </div>
                    {e.description && (
                      <div style={{ margin: '4px 0', color: 'var(--text)', whiteSpace: 'pre-wrap' }}>
                        {renderDescription(e.description)}
                      </div>
                    )}
                    <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                      {formatGameTime(e.fire_at_game)}
                    </div>
                    {isWeather && (
                      <div className="row" style={{ gap: 6, marginTop: 6 }}>
                        <button
                          disabled={rollWeather.isPending}
                          onClick={() => rollWeather.mutate()}
                          style={{
                            fontSize: 11,
                            padding: '4px 8px',
                            background: 'var(--accent)',
                            color: 'white',
                            border: 'none',
                            borderRadius: 4,
                            cursor: 'pointer'
                          }}
                        >
                          {rollWeather.isPending ? 'Rolling...' : '🎲 Re-roll Weather'}
                        </button>
                        {weatherTableId && (
                          <Link
                            to="/entities/$entityId"
                            params={{ entityId: weatherTableId }}
                            style={{
                              fontSize: 11,
                              padding: '4px 8px',
                              background: 'var(--accent)',
                              color: 'white',
                              border: 'none',
                              borderRadius: 4,
                              textDecoration: 'none',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center'
                            }}
                          >
                            📋 Open Weather Table
                          </Link>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
