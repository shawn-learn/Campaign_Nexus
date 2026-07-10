import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  exportCampaign,
  importCampaign,
  useCampaigns,
  useCreateCampaign,
} from '../api/hooks'
import { downloadJson, exportFilename, pickJsonFile } from '../lib/jsonFile'
import { useCampaignStore } from '../stores/campaign'
import { useActiveCampaign } from './useActiveCampaign'

// Top-bar campaign switcher + inline create + JSON export/import (docs/09, §11.1; FR-1.6).
export function CampaignSwitcher() {
  const { data: campaigns } = useCampaigns()
  const { campaign } = useActiveCampaign()
  const setActive = useCampaignStore((s) => s.setActiveCampaign)
  const createCampaign = useCreateCampaign()
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    createCampaign.mutate(
      { name: name.trim() },
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
        <form className="row" onSubmit={submit}>
          <input
            autoFocus
            placeholder="New campaign name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
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
