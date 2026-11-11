import { describe, expect, it, vi } from 'vitest'
import { getHealth } from './api'

describe('getHealth', () => {
  it('requests and validates the health endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({ status: 'ok', service: 'scholarship-hunter-ai' }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(getHealth(new AbortController().signal)).resolves.toEqual({
      status: 'ok', service: 'scholarship-hunter-ai',
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/health', expect.objectContaining({
      headers: { Accept: 'application/json' }, signal: expect.any(AbortSignal),
    }))
  })

  it('rejects HTTP errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 503 })))
    await expect(getHealth(new AbortController().signal)).rejects.toThrow('HTTP 503')
  })

  it.each([null, {}, { status: 'ok' }, { status: 'down', service: 'scholarship-hunter-ai' }])(
    'rejects an invalid health payload: %j', async (payload) => {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(payload)))
      await expect(getHealth(new AbortController().signal)).rejects.toThrow('Unexpected health response')
    },
  )

  it('rejects non-JSON responses', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('<html>not an API</html>')))
    await expect(getHealth(new AbortController().signal)).rejects.toThrow()
  })
})
