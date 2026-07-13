import type { ReactNode } from 'react'

export interface SortOption {
  value: string
  label: string
}

// A shared search + sort + filter bar for the app's list views (entities, maps, encounters,
// bestiary). It owns no state — the page holds the query/sort/filter values so it can drive
// the backend or a client-side pipeline. Extra, view-specific filters go in `children`.
export function ListToolbar({
  query,
  onQuery,
  placeholder = 'Search…',
  sort,
  onSort,
  sortOptions,
  count,
  total,
  children,
}: {
  query: string
  onQuery: (q: string) => void
  placeholder?: string
  sort?: string
  onSort?: (s: string) => void
  sortOptions?: SortOption[]
  /** Result count after filtering — shown as "count of total" when both are given. */
  count?: number
  total?: number
  children?: ReactNode
}) {
  return (
    <div className="row filters list-toolbar" style={{ gap: 10, flexWrap: 'wrap' }}>
      <div className="search-field">
        <input
          type="search"
          className="toolbar-search"
          placeholder={placeholder}
          value={query}
          onChange={(e) => onQuery(e.target.value)}
          aria-label={placeholder}
        />
        {query && (
          <button type="button" className="tag-x search-clear" aria-label="clear search"
            onClick={() => onQuery('')}>
            ×
          </button>
        )}
      </div>

      {children}

      {sortOptions && onSort && (
        <label className="row muted" style={{ gap: 4 }}>
          Sort
          <select value={sort} onChange={(e) => onSort(e.target.value)} aria-label="Sort by">
            {sortOptions.map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
        </label>
      )}

      {count !== undefined && (
        <span className="muted toolbar-count" style={{ marginLeft: 'auto', fontSize: 12 }}>
          {total !== undefined && total !== count ? `${count} of ${total}` : `${count}`}
        </span>
      )}
    </div>
  )
}
