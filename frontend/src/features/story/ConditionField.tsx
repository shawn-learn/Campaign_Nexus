import { useConditionCheck } from '../../api/hooks'
import { useDebounced } from '../../lib/useDebounced'

interface Props {
  campaignId: string
  value: string
  onChange: (value: string) => void
}

const HELP = "flag('x') == true and quest('id').status == 'active'"

/**
 * A condition expression with live validation. The check is debounced and cached per
 * expression, and reports both whether it *parses* and whether it is *currently true* —
 * the second is what tells the GM why a beat is or isn't being suggested.
 */
export function ConditionField({ campaignId, value, onChange }: Props) {
  const debounced = useDebounced(value, 300)
  const blank = debounced.trim() === ''
  const { data: check, isFetching } = useConditionCheck(campaignId, debounced)

  return (
    <div>
      <label className="muted" style={{ fontSize: 12 }}>Condition</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={HELP}
        style={{ width: '100%', fontFamily: 'monospace', fontSize: 12 }}
      />
      <p className="muted" style={{ fontSize: 12, margin: '4px 0 0' }}>
        {blank ? (
          'Blank — this edge is unconditional (always true).'
        ) : isFetching || !check ? (
          'Checking…'
        ) : !check.valid ? (
          <span style={{ color: '#e0603a' }}>✕ {check.error}</span>
        ) : (
          <span style={{ color: '#6fce7a' }}>
            ✓ Valid — currently <strong>{check.result ? 'true' : 'false'}</strong>
          </span>
        )}
      </p>
    </div>
  )
}
