import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { RequireAuth, RequireRole } from '../components/AuthGuards'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

function renderWithRouter(ui, { route = '/' } = {}) {
  return render(
    <MemoryRouter initialEntries={[route]}>
      {ui}
    </MemoryRouter>
  )
}

describe('RequireAuth', () => {
  it('renders children when authenticated', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: true, loading: false })

    renderWithRouter(<RequireAuth><div>Protected content</div></RequireAuth>)

    expect(screen.getByText('Protected content')).toBeInTheDocument()
  })

  it('redirects to /auth when not authenticated', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: false, loading: false })

    renderWithRouter(<RequireAuth><div>Protected content</div></RequireAuth>)

    expect(screen.queryByText('Protected content')).not.toBeInTheDocument()
  })

  it('returns null while loading', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: false, loading: true })

    const { container } = renderWithRouter(
      <RequireAuth><div>Protected content</div></RequireAuth>
    )

    expect(container.innerHTML).toBe('')
  })
})

describe('RequireRole', () => {
  it('renders children when user has the required role', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: true, role: 'admin', loading: false })

    renderWithRouter(
      <RequireRole role="admin"><div>Admin content</div></RequireRole>
    )

    expect(screen.getByText('Admin content')).toBeInTheDocument()
  })

  it('redirects to /dashboard when role does not match', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: true, role: 'user', loading: false })

    renderWithRouter(
      <RequireRole role="admin"><div>Admin content</div></RequireRole>
    )

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument()
  })

  it('redirects to /auth when not authenticated', async () => {
    const { useAuth } = await import('../contexts/AuthContext')
    useAuth.mockReturnValue({ isLoggedIn: false, role: null, loading: false })

    renderWithRouter(
      <RequireRole role="admin"><div>Admin content</div></RequireRole>
    )

    expect(screen.queryByText('Admin content')).not.toBeInTheDocument()
  })
})
