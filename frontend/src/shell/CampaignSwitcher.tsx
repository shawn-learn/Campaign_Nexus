import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  exportCampaign,
  importCampaign,
  useCampaigns,
  useCreateCampaign,
  useRuleSystems,
} from '../api/hooks'
import { downloadJson, exportFilename, pickJsonFile } from '../lib/jsonFile'
import { useCampaignStore } from '../stores/campaign'
import { useActiveCampaign } from './useActiveCampaign'

// Top-bar campaign switcher + inline create + JSON export/import (docs/09, §11.1; FR-1.6).
export function CampaignSwitcher() {
  const { data: campaigns } = useCampaigns()
  const { data: systems } = useRuleSystems()
  const { campaign } = useActiveCampaign()
  const setActive = useCampaignStore((s) => s.setActiveCampaign)
  const createCampaign = useCreateCampaign()
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [systemId, setSystemId] = useState('dnd5e')
  const [calendarId, setCalendarId] = useState('generic')
  const [busy, setBusy] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createCampaign.mutate(
      {
        name: name.trim(),
        rule_system_id: systemId,
        calendar_id: calendarId,
      },
      { onSuccess: (c) => { setActive(c.id); setName(''); setCreating(false) } },
    )
  }

  const doExport = async () => {
    if (!campaign) return
    const data = await exportCampaign(campaign.id)
    downloadJson(exportFilename('campaign', campaign.name), data)
  }

  const doImport = async () => {
    setBusy(true)
    try {
      const payload = await pickJsonFile()
      const created = await importCampaign(payload)
      await qc.invalidateQueries({ queryKey: ['campaigns'] })
      setActive(created.id)
    } catch {
      // swallow: pickJsonFile rejects on cancel; import errors surface via the empty state
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="switcher">
      {creating ? (
        <form className="row" onSubmit={submit} style={{ gap: 8 }}>
          <input
            autoFocus
            placeholder="New campaign name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ minWidth: 160 }}
          />
          <select
            value={systemId}
            onChange={(e) => setSystemId(e.target.value)}
            aria-label="Rules"
            style={{ padding: '4px 8px' }}
          >
            {systems?.map((sys) => (
              <option key={sys.id} value={sys.id}>{sys.name}</option>
            )) ?? (
              <>
                <option value="dnd5e">D&D 5e</option>
                <option value="nimble">Nimble</option>
              </>
            )}
          </select>
          <select
            value={calendarId}
            onChange={(e) => setCalendarId(e.target.value)}
            aria-label="Calendar"
            style={{ padding: '4px 8px' }}
          >
            <option value="generic">Generic Calendar</option>
            <option value="harptos">Harptos Calendar</option>
            <option value="barovian">Barovian Calendar</option>
          </select>
          <button type="submit" disabled={createCampaign.isPending}>Create</button>
          <button type="button" className="ghost" onClick={() => setCreating(false)}>Cancel</button>
        </form>
      ) : (
        <div className="row">
          <select
            value={campaign?.id ?? ''}
            onChange={(e) => setActive(e.target.value)}
            aria-label="Active campaign"
          >
            {campaigns?.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <button type="button" className="ghost" onClick={() => setCreating(true)}>+ New</button>
          <button type="button" className="ghost" title="Export campaign JSON" onClick={() => void doExport()}>⬇</button>
          <button type="button" className="ghost" title="Import campaign JSON" disabled={busy} onClick={() => void doImport()}>⬆</button>
        </div>
      )}
    </div>
  )
}
