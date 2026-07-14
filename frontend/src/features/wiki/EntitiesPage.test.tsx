import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EntitiesPage } from './EntitiesPage'

const mutateCreate = vi.fn()

vi.mock('../../api/hooks', () => ({
  useCreateEntity: () => ({ mutate: mutateCreate, isPending: false }),
  useEntities: () => ({
    data: [
      {
        id: 'ent1',
        name: 'Serah Voss',
        entity_type: 'npc',
        tags: [],
        deleted: false,
      },
    ],
  }),
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
  it('renders a visible edit action for created entities in the list', () => {
    render(<EntitiesPage />)

    expect(screen.getByRole('link', { name: /edit/i })).toBeInTheDocument()
  })
})
