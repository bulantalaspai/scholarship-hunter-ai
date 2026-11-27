import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { requiredFields } from '../review'
import type { FieldAudit, ReviewDetail } from '../review'
import ReviewDashboard from './ReviewDashboard'

const accessKey = 'synthetic-review-ui-test-key'
const programme = 'Example Graduate Scholarship'
const endpoint = '/api/review/drafts'
const source = 'https://example.org/scholarship'
const date = '2026-11-01T12:00:00Z'
const summary = {
  draft_id: '0'.repeat(64), state: 'pending_review', source_kind: 'manual',
  published_id: null, scholarship_name: programme, university_or_provider: 'Example Foundation',
  official_source_url: source,
} as const

const pendingDraft: ReviewDetail = {
  ...summary,
  source_text: programme,
  created_at: date,
  draft: {
    official_source_url: source,
    retrieved_on: '2026-11-01',
    fields: { scholarship_name: { quote: programme, scope: 'programme' } },
  },
  expired_deadline: null,
  duplicate_candidates: [], conflicts: [], wording_checks: [], missing_fields: [],
  related_draft_ids: [], field_reviews: {}, field_history: [], blocked_fields: [],
  dashboard_approved: false, history: [],
}

async function unlock(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Local access key'), accessKey)
  await user.click(screen.getByRole('button', { name: 'Unlock review' }))
}

describe('local scholarship review', () => {
  it('only requests staged data after submission and clears it when locked', async () => {
    const fetchMock = vi.fn((path: string, options: RequestInit) => {
      expect(new Headers(options.headers).get('Authorization')).toBe('Bearer ' + accessKey)
      expect(options.cache).toBe('no-store')
      return Promise.resolve(Response.json(path === endpoint ? [summary] : pendingDraft))
    })
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<ReviewDashboard />)

    expect(fetchMock).not.toHaveBeenCalled()
    await unlock(user)
    expect(await screen.findByRole('heading', { name: programme })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Approve draft' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Publish record' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Lock review' }))
    expect(screen.getByLabelText('Local access key')).toHaveValue('')
    expect(screen.queryByRole('region', { name: 'Review queue' })).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('leaves the queue locked when local review rejects the access key', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({}, { status: 401 })))
    const user = userEvent.setup()
    render(<ReviewDashboard />)

    await unlock(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('The local access key was rejected.')
    expect(screen.queryByRole('region', { name: 'Review queue' })).toBeNull()
  })

  it('requires a separate confirmation and rationale for publication after approval', async () => {
    const audits: FieldAudit[] = requiredFields.map(({ key }) => ({
      field: key, decision: 'accepted', value: programme, evidence: [programme],
      reviewer: 'Synthetic reviewer', rationale: 'Reviewed fixture excerpt.', decided_at: date,
    }))
    const reviewed = {
      ...pendingDraft,
      field_reviews: Object.fromEntries(audits.map((item) => [item.field, item])),
      field_history: audits,
    }
    const approved = {
      ...reviewed, state: 'approved', dashboard_approved: true,
      history: [{ action: 'approved', reviewer: 'Synthetic reviewer', rationale: 'Approved staged evidence.',
        decided_at: date, approved_record: { scholarship_name: programme } }],
    }
    const fetchMock = vi.fn((path: string) => Promise.resolve(Response.json(
      path === endpoint ? [summary] : path.endsWith('/approve') ? approved
        : path.endsWith('/publish') ? { ...approved, published_id: 42 } : reviewed,
    )))
    vi.stubGlobal('fetch', fetchMock)
    const user = userEvent.setup()
    render(<ReviewDashboard />)
    await unlock(user)
    await user.type(await screen.findByLabelText('Reviewer name or ID'), 'Synthetic reviewer')
    await user.type(await screen.findByLabelText('Approval rationale'), 'Approved staged evidence.')
    await user.click(screen.getByLabelText('I checked the cited evidence for this draft'))
    await user.click(screen.getByRole('button', { name: 'Approve draft' }))

    expect(await screen.findByText('Inspect the approved record')).toBeVisible()
    expect(screen.getByLabelText('Publication rationale')).toHaveValue('')
    expect(screen.getByLabelText('Publish this reviewed record to the catalogue')).not.toBeChecked()
    expect(fetchMock).toHaveBeenCalledTimes(3)
    await user.type(screen.getByLabelText('Publication rationale'), 'Verified the approval snapshot.')
    await user.click(screen.getByLabelText('Publish this reviewed record to the catalogue'))
    await user.click(screen.getByRole('button', { name: 'Publish record' }))

    expect(await screen.findByRole('link', { name: '42' })).toHaveAttribute('href', '#/scholarships/42')
    expect(fetchMock).toHaveBeenLastCalledWith(endpoint + '/' + summary.draft_id + '/publish',
      expect.objectContaining({ method: 'POST', body: JSON.stringify({
        rationale: 'Verified the approval snapshot.', confirm: true, reviewer: 'Synthetic reviewer',
      }) }))
  })
})
