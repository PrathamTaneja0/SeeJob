import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StatusBadge } from '../components/StatusBadge'

describe('StatusBadge', () => {
  it('renders status label', () => {
    render(<StatusBadge status="docs_ready" />)
    expect(screen.getByText('docs ready')).toBeInTheDocument()
  })
})
