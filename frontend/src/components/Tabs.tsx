import React, { useRef } from 'react'

interface Tab {
  id: string
  label: string
}

interface TabsProps {
  tabs: Tab[]
  activeTab: string
  onChange: (id: string) => void
  children: React.ReactNode
  /** Distinguishes multiple tab groups on one page for stable a11y ids. */
  idPrefix?: string
}

export function Tabs({ tabs, activeTab, onChange, children, idPrefix = 'tabs' }: TabsProps) {
  const btnRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next: number | null = null
    if (e.key === 'ArrowRight') next = (index + 1) % tabs.length
    else if (e.key === 'ArrowLeft') next = (index - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = tabs.length - 1
    if (next === null) return
    e.preventDefault()
    const target = tabs[next]
    onChange(target.id)
    btnRefs.current[target.id]?.focus()
  }

  return (
    <div className="tabs">
      <div className="tab-bar" role="tablist">
        {tabs.map((tab, i) => {
          const selected = activeTab === tab.id
          return (
            <button
              key={tab.id}
              ref={(el) => { btnRefs.current[tab.id] = el }}
              role="tab"
              id={`${idPrefix}-tab-${tab.id}`}
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              className={`tab-btn ${selected ? 'active' : ''}`}
              onClick={() => onChange(tab.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div className="tab-content">
        {children}
      </div>
    </div>
  )
}

interface TabPanelProps {
  id: string
  activeTab: string
  children: React.ReactNode
  idPrefix?: string
}

export function TabPanel({ id, activeTab, children, idPrefix = 'tabs' }: TabPanelProps) {
  if (id !== activeTab) return null
  return (
    <div
      className="tab-panel"
      role="tabpanel"
      id={`${idPrefix}-panel-${id}`}
      aria-labelledby={`${idPrefix}-tab-${id}`}
      tabIndex={0}
    >
      {children}
    </div>
  )
}
