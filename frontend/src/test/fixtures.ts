// Entirely fictional records for frontend tests. Never imported by application UI.
import type {
  EligibilityResult,
  EligibilityStatus,
  MatchResult,
  RequirementResult,
  Scholarship,
} from '../types'

export const demoScholarship: Scholarship = {
  id: 1,
  scholarship_name: 'Fictional Demo Engineering Scholarship',
  university_or_provider: 'Fictional Demo University',
  destination_country: ['Germany'],
  degree_level: 'master',
  eligible_study_fields: ['Engineering'],
  eligible_nationalities: null,
  minimum_gpa: null,
  gpa_scale: null,
  minimum_ielts: null,
  funding_type: 'fully_funded',
  tuition_coverage: 'Fictional test tuition coverage.',
  living_stipend: 'Fictional test stipend.',
  application_deadline: null,
  application_cycle: '2027-2028',
  official_source_url: 'https://example.org/fictional-scholarship',
  last_verified_at: '2026-11-11',
  additional_requirements: 'Fictional requirements, used in tests only.',
  notes: null,
}

export function demoAssessment(
  status: EligibilityStatus = 'needs_verification',
  id = 1,
): EligibilityResult {
  const state =
    status === 'eligible'
      ? 'met'
      : status === 'ineligible'
        ? 'failed'
        : 'unknown'
  const requirements = (
    [
      ['prior_degree', 'admission'],
      ['funding_availability', 'funding'],
      ['application_open', 'application'],
    ] as const
  ).map<RequirementResult>(([requirement, scope]) => ({
    requirement,
    scope,
    status: state,
    explanation: 'Fictional documented check for testing.',
    suggestion: state === 'unknown' ? 'Confirm the source conditions.' : null,
  }))
  const names = requirements.map((item) => item.requirement)
  return {
    scholarship_id: id,
    scholarship_name: demoScholarship.scholarship_name,
    status,
    admission_status: status,
    funding_status: status,
    application_status: status,
    requirements,
    matched_requirements: state === 'met' ? names : [],
    failed_requirements: state === 'failed' ? names : [],
    unknown_requirements: state === 'unknown' ? names : [],
    suggestions: state === 'unknown' ? ['Confirm the source conditions.'] : [],
    explanation:
      state === 'unknown'
        ? 'Mandatory conditions remain unverified.'
        : state === 'failed'
          ? 'A confirmed requirement is not satisfied.'
          : 'All modeled mandatory requirements are verified.',
    official_source_url: demoScholarship.official_source_url,
    last_verified_at: demoScholarship.last_verified_at,
    rule_source_urls: [],
    rules_verified_at: null,
    evaluated_on: '2026-11-12',
    disclaimer:
      'An eligibility assessment does not guarantee admission or funding.',
  }
}

export function demoMatches(): MatchResult {
  return {
    eligible: [],
    needs_verification: [
      {
        assessment: demoAssessment(),
        ranking_reasons: [
          'Eligibility group: needs_verification.',
          'Exact documented study-field match.',
        ],
      },
    ],
    ineligible: [],
    counts: { eligible: 0, needs_verification: 1, ineligible: 0 },
    total: 1,
    page: 1,
    page_size: 10,
  }
}
