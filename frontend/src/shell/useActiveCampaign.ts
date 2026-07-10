import { useEffect } from 'react'
import { useCampaigns } from '../api/hooks'
import { useCampaignStore } from '../stores/campaign'
import type { Campaign } from '../api/client'

// Resolves the active campaign: the stored selection if still valid, otherwise the
// first campaign. Seeds the store on first load so the rest of the app can assume one.
export function useActiveCampaign(): { campaign: Campaign | null; isLoading: boolean } {
  const { data: campaigns, isLoading } = useCampaigns()
  const activeId = useCampaignStore((s) => s.activeCampaignId)
  const setActive = useCampaignStore((s) => s.setActiveCampaign)

  const valid = campaigns?.find((c) => c.id === activeId) ?? campaigns?.[0] ?? null

  useEffect(() => {
    if (valid && valid.id !== activeId) setActive(valid.id)
  }, [valid, activeId, setActive])

  return { campaign: valid, isLoading }
}
