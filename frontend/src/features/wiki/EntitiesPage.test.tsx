import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EntitiesPage } from './EntitiesPage'

const mutateCreate = vi.fn()
const mutatePurge = vi.fn()

// One live entity and one soft-deleted one, so the purge affordance has something to count.
vi.mock('../../api/hooks', () => ({
  useCreateEntity: () => ({ mutate: mutateCreate, isPending: false }),
  useEntities: (_campaignId: string, opts?: { include_deleted?: boolean }) => ({
    data: [
      {
        id: 'ent1',
        name: 'Serah Voss',
        entity_type: 'npc',
        tags: [],
        deleted: false,
      },
      ...(opts?.include_deleted
        ? [{ id: 'ent2', name: 'Old Note', entity_type: 'note', tags: [], deleted: true }]
        : []),
    ],
  }),
  usePurgeDeletedEntities: () => ({ mutate: mutatePurge, isPending: false }),
  useTags: () => ({ data: [] }),
}))

vi.mock('../../shell/useActiveCampaign', () => ({
  useActiveCampaign: () => ({ campaign: { id: 'camp1' } }),
}))

vi.mock('@tanstack/react-router', () => ({
  Link: ({ to, params, children, ...props }: { to: string; params?: Record<string, string>; children: React.ReactNode }) => {
    const href = typeof to === 'string' ? to.replace('$entityId', params?.entityId ?? '') : '#'
    return <a href={href} {...props}>{children}</a>
  },
  useSearch: () => ({}),
}))

describe('EntitiesPage', () => {
  beforeEach(() => {
    mutatePurge.mockClear()
  })

  it('renders a visible edit action for created entities in the list', () => {
    render(<EntitiesPage />)

    expect(screen.getByRole('link', { name: /edit/i })).toBeInTheDocument()
  })

  it('offers to purge soft-deleted entities, counting them even while they are hidden', () => {
    render(<EntitiesPage />)

    // "Show deleted" is off, but the purge button still knows there is one to reclaim.
    expect(screen.getByRole('button', { name: /purge 1 deleted/i })).toBeInTheDocument()
  })

  it('purges only after the confirmation is accepted', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    render(<EntitiesPage />)

    await userEvent.click(screen.getByRole('button', { name: /purge 1 deleted/i }))
    expect(confirmSpy).toHaveBeenCalled()
    expect(mutatePurge).not.toHaveBeenCalled()

    confirmSpy.mockReturnValue(true)
    await userEvent.click(screen.getByRole('button', { name: /purge 1 deleted/i }))
    expect(mutatePurge).toHaveBeenCalledTimes(1)

    confirmSpy.mockRestore()
  })
})
