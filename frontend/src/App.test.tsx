import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import App from './App'

function healthyResponse() {
  return Response.json({ status: 'ok', service: 'scholarship-hunter-ai' })
}

describe('connection check', () => {
  it('shows a pending state and prevents duplicate checks', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Scholarship Hunter AI' })).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent('Checking the API connection')
    expect(screen.getByRole('button', { name: 'Checking…' })).toBeDisabled()
  })

  it('shows a successful connection', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(healthyResponse()))
    render(<App />)

    expect(await screen.findByText(/API connected/)).toBeVisible()
    expect(screen.getByRole('button', { name: 'Check again' })).toBeEnabled()
  })

  it('recovers from a network error when the user retries', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValueOnce(healthyResponse())
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    expect(await screen.findByText(/Connection check failed/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: 'Check again' }))
    expect(await screen.findByText(/API connected/)).toBeVisible()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shows failure for an incompatible API response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ status: 'unexpected' })))
    render(<App />)
    expect(await screen.findByText(/Connection check failed/)).toBeVisible()
  })

  it('cancels the pending request on unmount', () => {
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}))
    vi.stubGlobal('fetch', fetchMock)
    const { unmount } = render(<App />)
    const signal: AbortSignal = fetchMock.mock.calls[0][1].signal

    expect(signal.aborted).toBe(false)
    unmount()
    expect(signal.aborted).toBe(true)
  })
})
