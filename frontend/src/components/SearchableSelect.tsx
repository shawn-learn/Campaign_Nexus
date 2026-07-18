import { useState, useRef, useEffect } from 'react'

export interface SelectOption {
  id: string
  name: string
}

interface SearchableSelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  label?: string
  disabled?: boolean
}

export function SearchableSelect({
  value,
  onChange,
  options,
  placeholder = '— choose —',
  label,
  disabled = false,
}: SearchableSelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const useSearchable = options.length > 15

  const filtered = query.trim()
    ? options.filter((opt) =>
        opt.name.toLowerCase().includes(query.toLowerCase())
      )
    : options

  const selectedOption = options.find((opt) => opt.id === value)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex((i) =>
        i < filtered.length - 1 ? i + 1 : i
      )
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex((i) => (i > 0 ? i - 1 : 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (filtered[highlightedIndex]) {
        onChange(filtered[highlightedIndex].id)
        setIsOpen(false)
        setQuery('')
      }
    } else if (e.key === 'Escape') {
      setIsOpen(false)
      setQuery('')
    }
  }

  useEffect(() => {
    if (!isOpen) setHighlightedIndex(0)
  }, [isOpen])

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false)
        setQuery('')
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () =>
      document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Use native select for small lists
  if (!useSearchable) {
    return (
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">{placeholder}</option>
        {options.map((opt) => (
          <option key={opt.id} value={opt.id}>
            {opt.name}
          </option>
        ))}
      </select>
    )
  }

  // Searchable dropdown for large lists
  return (
    <div
      ref={containerRef}
      style={{ position: 'relative', display: 'inline-block', width: '100%' }}
    >
      <input
        ref={inputRef}
        type="text"
        placeholder={
          isOpen
            ? 'Search…'
            : selectedOption?.name || placeholder
        }
        value={isOpen ? query : ''}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlightedIndex(0)
        }}
        onFocus={() => setIsOpen(true)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        style={{
          cursor: disabled ? 'not-allowed' : 'pointer',
          width: '100%',
        }}
        aria-label={label}
      />

      {isOpen && filtered.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            backgroundColor: 'var(--color-background, white)',
            border: '1px solid var(--color-border)',
            borderTop: 'none',
            maxHeight: 200,
            overflowY: 'auto',
            zIndex: 1000,
            boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
          }}
        >
          {filtered.map((opt, index) => (
            <div
              key={opt.id}
              onClick={() => {
                onChange(opt.id)
                setIsOpen(false)
                setQuery('')
              }}
              style={{
                padding: '8px 12px',
                cursor: 'pointer',
                backgroundColor:
                  index === highlightedIndex
                    ? 'var(--color-highlight, #f0f0f0)'
                    : 'transparent',
                borderBottom:
                  index < filtered.length - 1
                    ? '1px solid var(--color-border)'
                    : 'none',
              }}
              onMouseEnter={() => setHighlightedIndex(index)}
            >
              {opt.name}
            </div>
          ))}
        </div>
      )}

      {isOpen && filtered.length === 0 && query.trim() && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            right: 0,
            backgroundColor: 'var(--color-background, white)',
            border: '1px solid var(--color-border)',
            borderTop: 'none',
            padding: '8px 12px',
            color: 'var(--color-muted, #666)',
            zIndex: 1000,
          }}
        >
          No matches for "{query}"
        </div>
      )}
    </div>
  )
}
