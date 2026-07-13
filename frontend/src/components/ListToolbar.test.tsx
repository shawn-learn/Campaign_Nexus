import { render, cleanup, fireEvent, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ListToolbar } from './ListToolbar'

afterEach(cleanup)

const SORTS = [
  { value: 'name', label: 'Name A–Z' },
  { value: '-name', label: 'Name Z–A' },
]

describe('ListToolbar', () => {
  it('reports query changes and shows a clear button only when non-empty', () => {
    const onQuery = vi.fn()
    const { container, rerender } = render(
      <ListToolbar query="" onQuery={onQuery} placeholder="Search maps…" />,
    )
    const ui = within(container)
    expect(ui.queryByLabelText('clear search')).not.toBeInTheDocument()

    fireEvent.change(ui.getByPlaceholderText('Search maps…'), { target: { value: 'ravenloft' } })
    expect(onQuery).toHaveBeenCalledWith('ravenloft')

    rerender(<ListToolbar query="ravenloft" onQuery={onQuery} placeholder="Search maps…" />)
    fireEvent.click(within(container).getByLabelText('clear search'))
    expect(onQuery).toHaveBeenLastCalledWith('')
  })

  it('renders sort options and reports selection', () => {
    const onSort = vi.fn()
    const ui = within(
      render(
        <ListToolbar query="" onQuery={() => {}} sort="name" onSort={onSort} sortOptions={SORTS} />,
      ).container,
    )
    fireEvent.change(ui.getByLabelText('Sort by'), { target: { value: '-name' } })
    expect(onSort).toHaveBeenCalledWith('-name')
  })

  it('shows "count of total" only when they differ', () => {
    const { container, rerender } = render(
      <ListToolbar query="" onQuery={() => {}} count={9} total={33} />,
    )
    expect(within(container).getByText('9 of 33')).toBeInTheDocument()

    rerender(<ListToolbar query="" onQuery={() => {}} count={33} total={33} />)
    expect(within(container).getByText('33')).toBeInTheDocument()
  })

  it('renders extra filter controls passed as children', () => {
    const ui = within(
      render(
        <ListToolbar query="" onQuery={() => {}}>
          <select aria-label="Kind"><option>world</option></select>
        </ListToolbar>,
      ).container,
    )
    expect(ui.getByLabelText('Kind')).toBeInTheDocument()
  })
})
