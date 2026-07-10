import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import BlindReviewToggle from '../components/BlindReviewToggle.jsx'

describe('BlindReviewToggle', () => {
  it('renders with default state (off)', () => {
    render(<BlindReviewToggle />)
    expect(screen.getByText('Blind Review')).toBeInTheDocument()
  })

  it('toggles on click and calls onToggle', () => {
    const onToggle = vi.fn()
    render(<BlindReviewToggle onToggle={onToggle} />)
    const switchEl = screen.getByRole('checkbox')
    expect(switchEl).not.toBeChecked()

    fireEvent.click(switchEl)
    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('respects enabled prop', () => {
    render(<BlindReviewToggle enabled={true} />)
    expect(screen.getByRole('checkbox')).toBeChecked()
  })
})
