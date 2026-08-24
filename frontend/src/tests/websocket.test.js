import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

class MockWebSocket {
  constructor(url) {
    this.url = url
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    this.readyState = 0
    MockWebSocket.instances.push(this)
  }
  close() {
    this.readyState = 3
    if (this.onclose) this.onclose({ code: 1000 })
  }
  send() {}
  simulateOpen() {
    this.readyState = 1
    if (this.onopen) this.onopen({})
  }
  simulateMessage(data) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(data) })
  }
  simulateClose(code = 1000) {
    this.readyState = 3
    if (this.onclose) this.onclose({ code })
  }
  simulateError() {
    if (this.onerror) this.onerror({})
  }
}
MockWebSocket.instances = []

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useBatchProgress', () => {
  it('starts with default state', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { result } = renderHook(() => useBatchProgress('batch-1'))

    expect(result.current).toEqual({
      processed: 0,
      total: 0,
      connected: false,
      failed: false,
    })
  })

  it('creates WebSocket connection with batch ID', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    renderHook(() => useBatchProgress('batch-1'))

    expect(MockWebSocket.instances.length).toBe(1)
    expect(MockWebSocket.instances[0].url).toContain('batch-1')
  })

  it('does not connect when batchId is empty', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    renderHook(() => useBatchProgress(null))

    expect(MockWebSocket.instances.length).toBe(0)
  })

  it('sets connected=true on open', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { result } = renderHook(() => useBatchProgress('batch-1'))

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    expect(result.current.connected).toBe(true)
    expect(result.current.failed).toBe(false)
  })

  it('updates progress on message', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { result } = renderHook(() => useBatchProgress('batch-1'))

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    act(() => {
      MockWebSocket.instances[0].simulateMessage({ processed: 5, total: 10 })
    })

    expect(result.current.processed).toBe(5)
    expect(result.current.total).toBe(10)
    expect(result.current.connected).toBe(true)
  })

  it('sets connected=false on close', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { result } = renderHook(() => useBatchProgress('batch-1'))

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    act(() => {
      MockWebSocket.instances[0].simulateClose()
    })

    expect(result.current.connected).toBe(false)
  })

  it('retries on close with exponential backoff', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    renderHook(() => useBatchProgress('batch-1'))

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    act(() => {
      MockWebSocket.instances[0].simulateClose()
    })

    expect(MockWebSocket.instances.length).toBe(1)

    await act(async () => {
      vi.advanceTimersByTime(2000)
    })

    expect(MockWebSocket.instances.length).toBe(2)
  })

  it('caps retries at MAX_RETRIES (10) and sets failed=true', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { result } = renderHook(() => useBatchProgress('batch-1'))

    for (let i = 0; i <= 10; i++) {
      const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]
      act(() => { ws.simulateClose() })
      await act(async () => { vi.advanceTimersByTime(60000) })
    }

    expect(result.current.failed).toBe(true)
  })

  it('does not reconnect after unmount', async () => {
    const { useBatchProgress } = await import('../utils/websocket.js')
    const { unmount } = renderHook(() => useBatchProgress('batch-1'))

    act(() => {
      MockWebSocket.instances[0].simulateOpen()
    })

    unmount()

    const countBefore = MockWebSocket.instances.length
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })

    expect(MockWebSocket.instances.length).toBe(countBefore)
  })
})
