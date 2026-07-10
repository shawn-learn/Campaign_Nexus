// Active-campaign selection — the one piece of genuine client state (ADR-007).
// Persisted to localStorage so a reload keeps the GM in the same campaign.
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface CampaignState {
  activeCampaignId: string | null
  setActiveCampaign: (id: string) => void
}

export const useCampaignStore = create<CampaignState>()(
  persist(
    (set) => ({
      activeCampaignId: null,
      setActiveCampaign: (id) => set({ activeCampaignId: id }),
    }),
    { name: 'nexus.activeCampaign' },
  ),
)
