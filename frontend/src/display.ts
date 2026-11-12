import type { EligibilityStatus, FundingType } from './types'

export const statusLabels: Record<EligibilityStatus, string> = {
  eligible: 'Eligible',
  ineligible: 'Ineligible',
  needs_verification: 'Needs verification',
}
export const fundingLabels: Record<FundingType, string> = {
  fully_funded: 'Fully funded',
  partially_funded: 'Partially funded',
  unknown: 'Funding unconfirmed',
}

export function calendarDate(value: string | null) {
  if (!value) return 'Not confirmed'
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.getTime())
    ? 'Not confirmed'
    : new Intl.DateTimeFormat('en-GB', {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      }).format(date)
}
