import { describe, it, expect, vi, beforeEach } from 'vitest'

beforeEach(() => {
  localStorage.clear()
  document.cookie = ''
})

describe('authFetch', () => {
  it('sends request with Authorization and CSRF headers', async () => {
    localStorage.setItem('plagioscale_access_token', 'test-token')
    document.cookie = 'csrf_token=csrf-123'

    const fakeRes = { ok: true, status: 200, json: async () => ({}) }
    global.fetch = vi.fn().mockResolvedValue(fakeRes)

    const { authFetch } = await import('../utils/auth.js')
    await authFetch('http://localhost:8000/data')

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/data',
      expect.objectContaining({
        credentials: 'include',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
          'X-CSRF-Token': 'csrf-123',
        }),
      })
    )
  })

  it('refreshes token on 401 and retries', async () => {
    localStorage.setItem('plagioscale_access_token', 'expired-token')

    const res401 = { ok: false, status: 401, json: async () => ({}) }
    const res200 = { ok: true, status: 200, json: async () => ({ success: true }) }
    const refreshRes = { ok: true, json: async () => ({ access_token: 'new-token' }) }

    global.fetch = vi.fn()
      .mockResolvedValueOnce(res401)
      .mockResolvedValueOnce(refreshRes)
      .mockResolvedValueOnce(res200)

    const { authFetch } = await import('../utils/auth.js')
    const result = await authFetch('http://localhost:8000/data')

    expect(global.fetch).toHaveBeenCalledTimes(3)
    expect(result.status).toBe(200)
    expect(localStorage.getItem('plagioscale_access_token')).toBe('new-token')
  })

  it('redirects to /auth when still 401 after refresh', async () => {
    localStorage.setItem('plagioscale_access_token', 'bad-token')

    const res401 = { ok: false, status: 401, json: async () => ({}) }
    global.fetch = vi.fn().mockResolvedValue(res401)

    delete window.location
    window.location = { href: '' }

    const { authFetch } = await import('../utils/auth.js')
    await authFetch('http://localhost:8000/data')

    expect(localStorage.getItem('plagioscale_access_token')).toBeNull()
    expect(window.location.href).toBe('/auth')
  })

  it('does not add Authorization header when no token exists', async () => {
    const fakeRes = { ok: true, status: 200, json: async () => ({}) }
    global.fetch = vi.fn().mockResolvedValue(fakeRes)

    const { authFetch } = await import('../utils/auth.js')
    await authFetch('http://localhost:8000/data')

    const calledHeaders = global.fetch.mock.calls[0][1].headers
    expect(calledHeaders).not.toHaveProperty('Authorization')
  })

  it('preserves caller-provided headers', async () => {
    localStorage.setItem('plagioscale_access_token', 'tok')

    const fakeRes = { ok: true, status: 200, json: async () => ({}) }
    global.fetch = vi.fn().mockResolvedValue(fakeRes)

    const { authFetch } = await import('../utils/auth.js')
    await authFetch('http://localhost:8000/data', {
      headers: { 'X-Custom': 'value' },
    })

    const calledHeaders = global.fetch.mock.calls[0][1].headers
    expect(calledHeaders['X-Custom']).toBe('value')
    expect(calledHeaders['Authorization']).toBe('Bearer tok')
  })
})
