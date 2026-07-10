// Transient client UI state (ADR-007): the command palette and the entity peek panel.
import { create } from 'zustand'

interface UiState {
  paletteOpen: boolean
  setPaletteOpen: (open: boolean) => void
  peekId: string | null
  openPeek: (entityId: string) => void
  closePeek: () => void
}

export const useUiStore = create<UiState>((set) => ({
  paletteOpen: false,
  setPaletteOpen: (open) => set({ paletteOpen: open }),
  peekId: null,
  openPeek: (entityId) => set({ peekId: entityId, paletteOpen: false }),
  closePeek: () => set({ peekId: null }),
}))
