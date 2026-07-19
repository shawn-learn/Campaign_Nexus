import { useState } from 'react'
import { useSetStoryFlag } from '../../api/hooks'
import { FlagValueInput } from './ConsequenceEditor'

interface Props {
  campaignId: string
  flags: Record<string, unknown>
}

/** Campaign flags — the world state edge conditions read. Editable so the GM can test. */
export function FlagsPanel({ campaignId, flags }: Props) {
  const setFlag = useSetStoryFlag(campaignId)
  const [key, setKey] = useState('')
  const [value, setValue] = useState<unknown>(true)

  const entries = Object.entries(flags ?? {})

  return (
    <div className="card">
      <h3 style={{ margin: '0 0 6px', fontSize: 15 }}>Flags</h3>
      {entries.length === 0 && (
        <p className="muted" style={{ fontSize: 12, margin: 0 }}>No flags set.</p>
      )}
      {entries.length > 0 && (
        <table style={{ width: '100%', fontSize: 12 }}>
          <tbody>
            {entries.map(([k, v]) => (
              <tr key={k}>
                <td style={{ fontFamily: 'monospace' }}>{k}</td>
                <td style={{ textAlign: 'right', fontFamily: 'monospace' }}>{JSON.stringify(v)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div style={{ marginTop: 8 }}>
        <input
          value={key}
          placeholder="flag key"
          style={{ width: '100%' }}
          onChange={(e) => setKey(e.target.value)}
        />
        <div style={{ marginTop: 6 }}>
          <FlagValueInput value={value} onChange={setValue} disabled={setFlag.isPending} />
        </div>
        <button
          style={{ marginTop: 6 }}
          disabled={!key.trim() || setFlag.isPending}
          onClick={async () => {
            await setFlag.mutateAsync({ key: key.trim(), value })
            setKey('')
          }}
        >
          Set flag
        </button>
      </div>
      {setFlag.isError && (
        <p style={{ color: '#e0603a', fontSize: 12 }}>{(setFlag.error as Error).message}</p>
      )}
    </div>
  )
}
