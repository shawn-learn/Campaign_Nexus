import { useBackups, useCreateBackup } from '../../api/hooks'

// Data lifecycle (FR-13): on-demand backups on top of the automatic pre-migration and
// session-start snapshots. Restore is an offline operation — documented in SECURITY.md —
// so this page lists and creates; it does not overwrite the live datastore from the browser.
function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

export function DataPage() {
  const { data: backups } = useBackups()
  const create = useCreateBackup()

  return (
    <>
      <h2>Data & Backups</h2>

      <div className="card">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <div>
            <strong>Backups</strong>
            <p className="muted" style={{ margin: '4px 0 0' }}>
              Snapshots of the whole datastore (database + media). Taken automatically before
              a migration and at session start; rotated to the newest few.
            </p>
          </div>
          <button disabled={create.isPending} onClick={() => create.mutate('manual')}>
            {create.isPending ? 'Backing up…' : 'Back up now'}
          </button>
        </div>

        <ul className="entities" style={{ marginTop: 10 }}>
          {backups?.length === 0 && <p className="muted">No backups yet.</p>}
          {backups?.map((b) => (
            <li key={b.id}>
              <span>
                <span className="mono">{b.id}</span>{' '}
                <span className="badge">{b.reason}</span>
              </span>
              <span className="muted">
                {fmtBytes(b.db_bytes)} · {b.media_files} media
              </span>
            </li>
          ))}
        </ul>
        <p className="muted" style={{ fontSize: 12 }}>
          To restore, stop the server and run{' '}
          <code>uv run python -m scripts.restore_backup &lt;id&gt;</code> (see SECURITY.md).
        </p>
      </div>
    </>
  )
}
