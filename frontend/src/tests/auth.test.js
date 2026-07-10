import { describe, it, expect, vi, beforeEach } from 'vitest'

const mockToken = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIiwicm9sZSI6InN0dWRlbnQiLCJleHAiOjk5OTk5OTk5OTl9.test'

beforeEach(() => {
  localStorage.clear()
})

describe('auth utilities', () => {
  it('stores and retrieves auth tokens', () => {
    localStorage.setItem('plagioscale_access_token', mockToken)
    expect(localStorage.getItem('plagioscale_access_token')).toBe(mockToken)
  })

  it('getAuthHeaders returns Authorization header when token exists', async () => {
    localStorage.setItem('plagioscale_access_token', mockToken)
    const mod = await import('../utils/auth.js')
    const headers = await mod.getAuthHeaders()
    expect(headers.Authorization).toBe(`Bearer ${mockToken}`)
  })

  it('getAuthHeaders returns empty object when no token', async () => {
    const mod = await import('../utils/auth.js')
    const headers = await mod.getAuthHeaders()
    expect(headers).toEqual({})
  })

  it('setToken/getToken roundtrip', async () => {
    const mod = await import('../utils/auth.js')
    mod.setToken(mockToken, 'test@example.com')
    expect(mod.getToken()).toBe(mockToken)
    expect(mod.getStoredEmail()).toBe('test@example.com')
  })

  it('clearToken removes token from storage', async () => {
    const mod = await import('../utils/auth.js')
    mod.setToken(mockToken)
    mod.clearToken()
    expect(mod.getToken()).toBe('')
  })

  it('refreshToken fetches new token from /auth/refresh', async () => {
    localStorage.setItem('plagioscale_access_token', mockToken)
    const fakeResponse = { ok: true, json: async () => ({ access_token: 'new-token' }) }
    global.fetch = vi.fn().mockResolvedValue(fakeResponse)

    const mod = await import('../utils/auth.js')
    const newToken = await mod.refreshToken()
    expect(newToken).toBe('new-token')
    expect(localStorage.getItem('plagioscale_access_token')).toBe('new-token')
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/auth/refresh'),
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: `Bearer ${mockToken}` })
      })
    )
  })
})
