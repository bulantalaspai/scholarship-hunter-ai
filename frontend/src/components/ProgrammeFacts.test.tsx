import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { demoAssessment, demoScholarship } from '../test/fixtures'
import { Assessment } from './ui'

describe('programme recommendation summaries', () => {
  it('loads only the displayed record and separates award terms from eligibility', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json(demoScholarship))
    vi.stubGlobal('fetch', fetch)
    render(<Assessment result={demoAssessment()} agentSummary />)
    expect(await screen.findByText('Germany')).toBeVisible()
    expect(screen.getByText('Fully funded')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledWith('/api/scholarships/1', expect.objectContaining({ method: 'GET' }))
    expect(screen.getAllByText('Needs verification')[0]).toBeVisible()
    const fundingScope = screen.getByText('Funding eligibility')
    expect(fundingScope).not.toBeVisible()
    await userEvent.setup().click(screen.getByText('Assessment details'))
    expect(fundingScope).toBeVisible()
  })

  it('labels missing catalogue fields explicitly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({
      ...demoScholarship, destination_country: null, funding_type: 'unknown',
    })))
    render(<Assessment result={demoAssessment()} agentSummary />)
    expect(await screen.findByText('Destination unconfirmed')).toBeVisible()
    expect(screen.getByText('Funding unconfirmed')).toBeVisible()
  })

  it.each([
    { scholarship_name: 'Fictional renamed programme' },
    { official_source_url: 'https://example.org/revised' },
    { last_verified_at: '2026-11-12' },
  ])('keeps a changed catalogue record separate from the assessment: %j', async (change) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...demoScholarship, ...change })))
    render(<Assessment result={demoAssessment()} agentSummary />)
    expect(await screen.findByText(/Catalogue details have changed/)).toBeVisible()
    expect(screen.queryByText('Fully funded')).toBeNull()
    expect(screen.getByRole('link', { name: /View official source/ })).toHaveAttribute('href', demoScholarship.official_source_url)
  })

  it('keeps the assessment and source visible when the detail request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({}, { status: 503 })))
    render(<Assessment result={demoAssessment('ineligible')} agentSummary />)
    expect(await screen.findByText(/Destination and funding details are unavailable/)).toBeVisible()
    expect(screen.getAllByText('Ineligible')[0]).toBeVisible()
    expect(screen.getByText('Unmet requirements')).toBeVisible()
    expect(screen.getByRole('link', { name: /View official source/ })).toBeVisible()
  })
})
