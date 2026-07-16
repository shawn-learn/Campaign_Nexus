import React, { useEffect, useRef } from 'react'

interface ModalProps {
  title: string
  onClose: () => void
  children: React.ReactNode
  /** Max width of the dialog card (px). */
  width?: number
}

/**
 * A minimal accessible modal: `role="dialog"` + `aria-modal`, Escape-to-close,
 * backdrop-click-to-close, and initial focus moved into the dialog so keyboard
 * users aren't stranded on the page behind it.
 */
export function Modal({ title, onClose, children, width = 480 }: ModalProps) {
  const cardRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    // Move focus into the dialog once mounted.
    cardRef.current?.focus()
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 200,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        ref={cardRef}
        className="card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        style={{ minWidth: 320, maxWidth: width, width: '90vw', maxHeight: '85vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <h4 style={{ margin: 0 }}>{title}</h4>
          <button className="ghost" aria-label="Close" onClick={onClose}>×</button>
        </div>
        {children}
      </div>
    </div>
  )
}
