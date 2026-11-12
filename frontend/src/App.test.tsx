import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'

beforeEach(() => window.history.replaceState(null, '', '/'))
afterEach(() => window.history.replaceState(null, '', '/'))

function healthyResponse() {
  return Response.json({ status: 'ok', service: 'scholarship-hunter-ai' })
}

describe('connection check', () => {
  it('shows a pending state and prevents duplicate checks', () => {
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise(() => {})))
    render(<App />)

    expect(
      screen.getByRole('heading', { name: 'Scholarship Hunter AI' }),
    ).toBeVisible()
    expect(screen.getByRole('status')).toHaveTextContent(
      'Checking the API connection',
    )
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
    const fetchMock = vi
      .fn()
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
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(Response.json({ status: 'unexpected' })),
    )
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

describe('local AI routing', () => {
  async function addProfile(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText('Nationality'), 'Kazakhstan')
    await user.selectOptions(screen.getByLabelText('Degree level'), 'bachelor')
    await user.type(screen.getByLabelText('Field of study'), 'Engineering')
    await user.selectOptions(
      screen.getByLabelText('Funding preference'),
      'any_funding',
    )
    await user.click(
      screen.getByRole('button', { name: 'Continue to local AI' }),
    )
  }

  it('requires a profile for direct AI links without contacting Ollama', () => {
    window.location.hash = '/agent'
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    expect(
      screen.getByRole('heading', { name: 'Add your profile for local AI' }),
    ).toBeVisible()
    expect(
      screen.getByRole('link', { name: 'Add student profile' }),
    ).toHaveAttribute('href', '#/profile?mode=ai')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('routes an AI-mode profile to the explicit-request page without an automatic model call', async () => {
    window.location.hash = '/profile?mode=ai'
    const user = userEvent.setup()
    const fetchMock = vi.fn().mockResolvedValue(
      Response.json({
        status: 'needs_verification',
        model: 'qwen3:4b-instruct',
        evaluated_on: '2026-11-12',
        steps: 1,
        tool_calls: 0,
        recommendations: [],
        message: 'No grounded selection was completed.',
        warnings: [],
        tool_trace: [],
        disclaimer: 'An AI assessment does not guarantee funding.',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    expect(
      screen.getByRole('heading', { name: 'Your profile for local AI' }),
    ).toBeVisible()
    await addProfile(user)
    expect(
      await screen.findByRole('heading', { name: 'Local AI recommendations' }),
    ).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(
      screen.getByRole('link', { name: 'Local AI' }),
    ).toHaveAttribute('aria-current', 'page')
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(
      await screen.findByText('No grounded selection was completed.'),
    ).toBeVisible()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).profile).toMatchObject({
      nationality: 'Kazakhstan',
      degree_completed: null,
      gpa: null,
      gpa_scale: null,
    })
  })

  it('allows profile removal before a new local AI request', async () => {
    window.location.hash = '/profile?mode=ai'
    const user = userEvent.setup()
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await addProfile(user)
    await screen.findByRole('heading', { name: 'Local AI recommendations' })
    await user.click(
      within(
        screen.getByRole('navigation', { name: 'Main navigation' }),
      ).getByRole('link', { name: 'My profile' }),
    )
    await user.click(screen.getByRole('button', { name: 'Clear profile' }))
    await user.click(
      screen.getByRole('link', { name: 'Local AI' }),
    )
    expect(
      await screen.findByRole('heading', {
        name: 'Add your profile for local AI',
      }),
    ).toBeVisible()
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
