// Recently-viewed entities, per campaign, persisted for the palette's empty state.
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface RecentItem {
  id: string
  name: string
  entity_type: string
}

interface RecentsState {
  byCampaign: Record<string, RecentItem[]>
  addRecent: (campaignId: string, item: RecentItem) => void
  recentsFor: (campaignId: string) => RecentItem[]
}

const MAX = 12

export const useRecentsStore = create<RecentsState>()(
  persist(
    (set, get) => ({
      byCampaign: {},
      addRecent: (campaignId, item) =>
        set((state) => {
          const prev = state.byCampaign[campaignId] ?? []
          const next = [item, ...prev.filter((r) => r.id !== item.id)].slice(0, MAX)
          return { byCampaign: { ...state.byCampaign, [campaignId]: next } }
        }),
      recentsFor: (campaignId) => get().byCampaign[campaignId] ?? [],
    }),
    { name: 'nexus.recents' },
  ),
)
