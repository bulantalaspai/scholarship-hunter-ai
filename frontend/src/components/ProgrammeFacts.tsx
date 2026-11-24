import { useCallback } from 'react'
import { getScholarship } from '../api'
import { fundingLabels } from '../display'
import { useResource } from '../hooks'
import type { EligibilityResult } from '../types'

/** The agent assessment carries eligibility, while the catalogue carries award terms. */
export default function ProgrammeFacts({ assessment }: { assessment: EligibilityResult }) {
  const id = assessment.scholarship_id
  const load = useCallback((signal: AbortSignal) => getScholarship(id, signal), [id])
  const { resource } = useResource(String(id), load)

  if (resource.status === 'loading') {
    return <p className="programme-facts-note">Loading destination and funding…</p>
  }
  if (resource.status === 'error') {
    return <p className="programme-facts-note">Destination and funding details are unavailable.</p>
  }
  const record = resource.data
  if (
    record.scholarship_name !== assessment.scholarship_name ||
    record.official_source_url !== assessment.official_source_url ||
    record.last_verified_at !== assessment.last_verified_at
  ) {
    return <p className="programme-facts-note">Catalogue details have changed. Verify destination and funding with the official source.</p>
  }
  return (
    <dl className="programme-facts" aria-label="Catalogue facts">
      <div>
        <dt className="sr-only">Destination</dt>
        <dd>{record.destination_country?.join(', ') || 'Destination unconfirmed'}</dd>
      </div>
      <div>
        <dt className="sr-only">Funding</dt>
        <dd>{fundingLabels[record.funding_type]}</dd>
      </div>
    </dl>
  )
}
